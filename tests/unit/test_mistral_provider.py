import os
from types import SimpleNamespace

import pytest

from models.providers.mistral import MistralProvider


class FakeChat:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def complete(self, **request):
        self.requests.append(request)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.chat = FakeChat(response)


def response_with(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content)
            )
        ]
    )


def test_mistral_provider_smoke(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    client = FakeClient(response_with("  Mistral response  "))

    provider = MistralProvider(
        model_name="mistral-small-latest",
        client=client,
    )

    result = provider.generate(
        "Return a short answer.",
        max_new_tokens=64,
        do_sample=False,
    )

    assert provider.name == "mistral"
    assert result == "Mistral response"
    assert client.chat.requests == [{
        "model": "mistral-small-latest",
        "messages": [{
            "role": "user",
            "content": "Return a short answer.",
        }],
        "max_tokens": 64,
        "temperature": 0.0,
    }]


def test_mistral_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        MistralProvider(client=FakeClient(response_with("unused")))


def test_mistral_provider_hides_api_failure_details(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    class FailingChat:
        def complete(self, **request):
            raise RuntimeError("secret request details")

    client = SimpleNamespace(chat=FailingChat())
    provider = MistralProvider(client=client)

    with pytest.raises(RuntimeError, match="Mistral API generation failed") as exc_info:
        provider.generate("hello")

    assert "secret request details" not in str(exc_info.value)
