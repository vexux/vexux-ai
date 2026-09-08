"""Lazy Ollama model provider."""

from __future__ import annotations

from typing import Any, Mapping

from core.contracts.capabilities import ModelProviderContract


class OllamaProvider:
    """ModelProviderContract implementation backed by a local Ollama server."""

    def __init__(
        self,
        model_name: str = "llama3.2",
        host: str = "http://127.0.0.1:11434",
        client: Any = None,
    ):
        self._name = "ollama"
        self.model_name = model_name
        self.host = host
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from ollama import Client

                self._client = Client(host=self.host)
            except Exception as exc:
                raise RuntimeError("Ollama client initialization failed.") from exc
        return self._client

    @staticmethod
    def _response_content(response: Any) -> Any:
        if isinstance(response, Mapping):
            message = response.get("message")
        else:
            message = getattr(response, "message", None)

        if isinstance(message, Mapping):
            return message.get("content")
        return getattr(message, "content", None)

    def generate(self, prompt: str, **kwargs) -> str:
        request = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        if "options" in kwargs:
            request["options"] = kwargs["options"]

        try:
            response = self._get_client().chat(**request)
            content = self._response_content(response)
        except Exception as exc:
            raise RuntimeError("Ollama generation failed.") from exc

        if not isinstance(content, str):
            raise RuntimeError("Ollama returned a non-text response.")
        return content.strip()
