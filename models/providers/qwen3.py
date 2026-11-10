"""Offline CPU provider for a locally cached Qwen3 causal language model."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

_DEFAULT_MODEL_PATH = (
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
        model_path: str | Path = _DEFAULT_MODEL_PATH,
        *,
        max_input_tokens: int = 2048,
        max_new_tokens: int = 256,
    ) -> None:
        if not isinstance(max_input_tokens, int) or isinstance(max_input_tokens, bool) or max_input_tokens < 1:
            raise ValueError("max_input_tokens must be a positive integer.")
        if not isinstance(max_new_tokens, int) or isinstance(max_new_tokens, bool) or max_new_tokens < 1:
            raise ValueError("max_new_tokens must be a positive integer.")
        expanded_path = os.path.expandvars(os.fspath(model_path))
        self.model_path = Path(expanded_path).expanduser()
        self.model_name = "Qwen3-0.6B"
        self.max_input_tokens = max_input_tokens
        self.max_new_tokens = max_new_tokens
        self._tokenizer: Any = None
        self._model: Any = None
        self._torch: Any = None
        self._load_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "qwen3"

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "provider": self.name,
            "model": self.model_name,
            "runtime_mode": "local",
        }

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(
                    str(self.model_path),
                    local_files_only=True,
                )
                if hasattr(tokenizer, "truncation_side"):
                    tokenizer.truncation_side = "left"
                model = AutoModelForCausalLM.from_pretrained(
                    str(self.model_path),
                    local_files_only=True,
                    dtype=torch.bfloat16,
                )
                model.to("cpu")
                model.eval()
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load local Qwen3 model from '{self.model_path}'. "
                    "Verify the cache and installed PyTorch/Transformers/safetensors."
                ) from exc

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
                f"Qwen3 generation failed for local model '{self.model_path}'."
            ) from exc
