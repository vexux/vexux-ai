import os
from typing import Any

from mistralai.client import Mistral

from core.contracts.capabilities import ModelProviderContract


class MistralProvider:
    """ModelProviderContract implementation backed by Mistral Chat Completions."""

    def __init__(
        self,
        model_name: str = "mistral-small-latest",
        client: Any = None,
    ):
        api_key = os.getenv("MISTRAL_API_KEY")

        if not api_key:
            raise ValueError(
                "MISTRAL_API_KEY is required for the Mistral provider."
            )

        self._name = "mistral"
        self.model_name = model_name
        self.client = client or Mistral(api_key=api_key)

    @property
    def name(self) -> str:
        return self._name

    def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> str:
        max_tokens = kwargs.pop(
            "max_tokens",
            kwargs.pop("max_new_tokens", 200),
        )
        do_sample = kwargs.pop("do_sample", True)
        temperature = kwargs.pop(
            "temperature",
            0.7 if do_sample else 0.0,
        )

        request = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = self.client.chat.complete(**request)
            content = response.choices[0].message.content
        except Exception as exc:
            raise RuntimeError(
                "Mistral API generation failed."
            ) from exc

        if not isinstance(content, str):
            raise RuntimeError(
                "Mistral API returned a non-text response."
            )

        return content.strip()
