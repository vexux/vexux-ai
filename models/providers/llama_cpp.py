"""Lazy CPU provider for a locally stored Llama GGUF model."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Mapping


_DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "weights"
    / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
)


class LlamaCppProvider:
    """Run a local GGUF model through llama-cpp-python."""

    def __init__(
        self,
        model_path: str | os.PathLike[str] = _DEFAULT_MODEL_PATH,
        *,
        n_ctx: int = 2048,
        n_threads: int = 4,
        max_new_tokens: int = 256,
    ) -> None:
        self.model_path = Path(
            os.path.expandvars(os.fspath(model_path))
        ).expanduser()
        self.n_ctx = self._positive_int(n_ctx, "n_ctx", maximum=8192)
        self.n_threads = self._positive_int(
            n_threads, "n_threads", maximum=16
        )
        self.max_new_tokens = self._positive_int(
            max_new_tokens, "max_new_tokens", maximum=1024
        )
        self.model_name = self.model_path.name
        self._model: Any = None
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()

    @staticmethod
    def _positive_int(value: int, name: str, *, maximum: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
        if value > maximum:
            raise ValueError(f"{name} must not exceed {maximum}.")
        return value

    @property
    def name(self) -> str:
        return "llama_cpp"

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "provider": self.name,
            "model": self.model_name,
            "runtime_mode": "local",
        }

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    f"Local GGUF model file does not exist: {self.model_path}. "
                    "Set LLAMA_CPP_MODEL_PATH to an approved local GGUF file."
                )
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise RuntimeError(
                    "The llama_cpp provider requires the optional "
                    "'llama-cpp-python' package in the active environment."
                ) from exc

            try:
                model = Llama(
                    model_path=str(self.model_path),
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    n_gpu_layers=0,
                    verbose=False,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load local GGUF model '{self.model_path}'."
                ) from exc
            self._model = model
            return model

    def generate(
        self,
        prompt: str,
        response_format: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if response_format is not None and response_format != "json":
            raise ValueError(
                "LlamaCppProvider supports only the optional 'json' response format."
            )

        requested_tokens = kwargs.pop(
            "max_new_tokens",
            kwargs.pop("max_tokens", self.max_new_tokens),
        )
        requested_tokens = self._positive_int(
            requested_tokens,
            "max_new_tokens",
            maximum=1_000_000,
        )
        max_tokens = min(requested_tokens, self.max_new_tokens)

        if response_format == "json":
            prompt = (
                f"{prompt}\n\n"
                "Respond with valid JSON only. Do not include Markdown or commentary."
            )

        messages = [{"role": "user", "content": prompt}]
        generation_options = dict(kwargs)
        generation_options.setdefault("max_tokens", max_tokens)
        generation_options.setdefault("temperature", 0.0)
        generation_options.setdefault("top_p", 1.0)

        try:
            model = self._get_model()
            with self._generation_lock:
                response = model.create_chat_completion(
                    messages=messages,
                    **generation_options,
                )
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Local Llama GGUF generation failed for '{self.model_path}'."
            ) from exc

        try:
            if isinstance(response, Mapping):
                content = response["choices"][0]["message"]["content"]
            else:
                content = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise RuntimeError(
                "llama-cpp-python returned an invalid chat completion response."
            ) from exc
        if not isinstance(content, str):
            raise RuntimeError(
                "llama-cpp-python returned a non-text chat completion."
            )
        return content.strip()
