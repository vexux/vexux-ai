"""Offline CPU provider for a locally cached Qwen3 causal language model."""

from __future__ import annotations

import gc
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

_DEFAULT_PRIMARY_MODEL_PATH = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "models"
    / "Qwen--Qwen3-4B"
    / "snapshots"
    / "master"
)
_DEFAULT_FALLBACK_MODEL_PATH = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "models"
    / "Qwen--Qwen3-0.6B"
    / "snapshots"
    / "master"
)


class Qwen3Provider:
    """Load and run a local Qwen3 model without network fallback."""

    def __init__(
        self,
        model_path: str | Path = _DEFAULT_PRIMARY_MODEL_PATH,
        *,
        fallback_model_path: str | Path = _DEFAULT_FALLBACK_MODEL_PATH,
        max_input_tokens: int = 1024,
        max_new_tokens: int = 128,
    ) -> None:
        if not isinstance(max_input_tokens, int) or isinstance(max_input_tokens, bool) or max_input_tokens < 1:
            raise ValueError("max_input_tokens must be a positive integer.")
        if not isinstance(max_new_tokens, int) or isinstance(max_new_tokens, bool) or max_new_tokens < 1:
            raise ValueError("max_new_tokens must be a positive integer.")
        expanded_path = os.path.expandvars(os.fspath(model_path))
        self.model_path = Path(expanded_path).expanduser()
        fallback_expanded_path = os.path.expandvars(os.fspath(fallback_model_path))
        self.fallback_model_path = Path(fallback_expanded_path).expanduser()
        self._primary_model_name = self._model_label(self.model_path)
        self._selected_model_name: str | None = None
        self._model_selection = "not_loaded"
        self.max_input_tokens = max_input_tokens
        self.max_new_tokens = max_new_tokens
        self._tokenizer: Any = None
        self._model: Any = None
        self._torch: Any = None
        self._load_error: str | None = None
        self._load_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "qwen3"

    @property
    def model_name(self) -> str:
        return self._selected_model_name or self._primary_model_name

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "provider": self.name,
            "model": self.model_name,
            "model_selection": self._model_selection,
            "runtime_mode": "local",
        }

    @staticmethod
    def _model_label(model_path: Path) -> str:
        for part in model_path.parts:
            normalized_part = part.casefold()
            if normalized_part == "qwen--qwen3-4b":
                return "Qwen3-4B"
            if normalized_part == "qwen--qwen3-0.6b":
                return "Qwen3-0.6B"
        return model_path.name or "Qwen3-local"

    @staticmethod
    def _validate_model_files(model_path: Path) -> None:
        if not model_path.is_dir():
            raise FileNotFoundError("Local model directory is missing.")
        if not (model_path / "config.json").is_file():
            raise FileNotFoundError("Required local model config.json is missing.")
        if not (model_path / "tokenizer.json").is_file():
            raise FileNotFoundError("Required local tokenizer.json is missing.")

        weight_index = next(
            (
                model_path / name
                for name in (
                    "model.safetensors.index.json",
                    "pytorch_model.bin.index.json",
                )
                if (model_path / name).is_file()
            ),
            None,
        )
        if weight_index is not None:
            with weight_index.open(encoding="utf-8") as index_file:
                index = json.load(index_file)
            weight_map = index.get("weight_map")
            if not isinstance(weight_map, dict) or not weight_map:
                raise ValueError("Local model weight index is invalid.")
            shards = {model_path / filename for filename in weight_map.values()}
            if any(not shard.is_file() for shard in shards):
                raise FileNotFoundError("One or more indexed local model shards are missing.")
            return

        if not any(
            (model_path / filename).is_file()
            for filename in ("model.safetensors", "pytorch_model.bin")
        ):
            raise FileNotFoundError("Required local model weights are missing.")

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, FileNotFoundError):
            return "required local model files are missing"
        if isinstance(exc, MemoryError):
            return "runtime memory allocation failed"
        if isinstance(exc, ImportError):
            return "a required local runtime dependency is unavailable"
        if isinstance(exc, OSError):
            return "local model or runtime I/O failed"
        if isinstance(exc, ValueError):
            return "model configuration or weights were rejected"
        return f"initialization raised {type(exc).__name__}"

    def _load_candidate(self, model_path: Path) -> tuple[Any, Any, Any]:
        tokenizer: Any = None
        model: Any = None
        torch: Any = None
        try:
            self._validate_model_files(model_path)
            import torch as torch_module
            from transformers import AutoModelForCausalLM, AutoTokenizer

            torch = torch_module
            tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                local_files_only=True,
            )
            if hasattr(tokenizer, "truncation_side"):
                tokenizer.truncation_side = "left"
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                local_files_only=True,
                dtype=torch.bfloat16,
            )
            model.to("cpu")
            model.eval()
            return tokenizer, model, torch
        except Exception:
            tokenizer = None
            model = None
            torch = None
            raise

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        if self._load_error is not None:
            raise RuntimeError(self._load_error)
        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return
            if self._load_error is not None:
                raise RuntimeError(self._load_error)
            primary_reason: str | None = None
            try:
                tokenizer, model, torch = self._load_candidate(self.model_path)
            except Exception as primary_exc:
                primary_reason = self._failure_reason(primary_exc)
            if primary_reason is None:
                self._selected_model_name = self._primary_model_name
                self._model_selection = "primary"
            else:
                gc.collect()
                primary_label = self._primary_model_name
                if self.model_path.resolve() == self.fallback_model_path.resolve():
                    self._load_error = (
                        f"Could not load configured local Qwen3 model "
                        f"'{primary_label}': {primary_reason}. Primary and "
                        "fallback paths resolve to the same directory; no "
                        "second load was attempted."
                    )
                    raise RuntimeError(self._load_error) from None
                fallback_label = self._model_label(self.fallback_model_path)
                _LOGGER.warning(
                    "Primary local Qwen3 model %s failed (%s); attempting "
                    "configured fallback %s.",
                    primary_label,
                    primary_reason,
                    fallback_label,
                )
                try:
                    tokenizer, model, torch = self._load_candidate(
                        self.fallback_model_path
                    )
                except Exception as fallback_exc:
                    fallback_reason = self._failure_reason(fallback_exc)
                    self._load_error = (
                        "Could not load either local Qwen3 model. "
                        f"Primary {primary_label} failed: {primary_reason}. "
                        f"Fallback {fallback_label} failed: {fallback_reason}."
                    )
                    raise RuntimeError(self._load_error) from None

                self._selected_model_name = fallback_label
                self._model_selection = "fallback"
                _LOGGER.warning(
                    "Loaded local Qwen3 fallback model %s after the primary "
                    "model failed.",
                    fallback_label,
                )

            self._torch = torch
            self._tokenizer = tokenizer
            self._model = model

    @staticmethod
    def _chat_text(tokenizer: Any, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError as exc:
            message = str(exc)
            if "enable_thinking" not in message or "unexpected keyword" not in message:
                raise
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

    def generate(
        self,
        prompt: str,
        response_format: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if response_format not in {None, "json"}:
            raise ValueError("Qwen3 supports only the optional 'json' response format.")
        requested_tokens = kwargs.pop("max_new_tokens", self.max_new_tokens)
        if (
            not isinstance(requested_tokens, int)
            or isinstance(requested_tokens, bool)
            or requested_tokens < 1
        ):
            raise ValueError("max_new_tokens must be a positive integer.")

        self._ensure_loaded()
        if response_format == "json":
            prompt = (
                f"{prompt}\n\n"
                "Respond with valid JSON only. Do not include Markdown or commentary."
            )

        try:
            text = self._chat_text(self._tokenizer, prompt)
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_input_tokens,
            )
            input_ids = inputs["input_ids"]
            input_length = input_ids.shape[-1]
            inputs = {
                key: value.to("cpu") if hasattr(value, "to") else value
                for key, value in inputs.items()
            }

            generation_kwargs = dict(kwargs)
            generation_kwargs["max_new_tokens"] = min(
                requested_tokens,
                self.max_new_tokens,
            )
            generation_kwargs.setdefault("do_sample", False)
            if self._tokenizer.pad_token_id is not None:
                generation_kwargs.setdefault(
                    "pad_token_id", self._tokenizer.pad_token_id
                )

            with self._torch.inference_mode():
                generated = self._model.generate(**inputs, **generation_kwargs)
            sequences = getattr(generated, "sequences", generated)
            new_tokens = sequences[0, input_length:]
            return self._tokenizer.decode(
                new_tokens,
                skip_special_tokens=True,
            ).strip()
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3 generation failed for selected local model "
                f"'{self.model_name}'."
            ) from exc
