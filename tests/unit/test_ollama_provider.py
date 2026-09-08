from types import ModuleType, SimpleNamespace

import pytest

from models.providers.ollama import OllamaProvider


class FakeOllamaClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, **request):
        self.calls.append(request)
        return self.response


def test_ollama_provider_contract_and_configured_request():
    client = FakeOllamaClient(
        SimpleNamespace(message=SimpleNamespace(content="  local response  "))
    )
    provider = OllamaProvider(
        model_name="qwen2.5:0.5b",
        host="http://ollama.test:11434",
        client=client,
    )

    assert provider.name == "ollama"
    assert callable(provider.generate)
    assert provider.generate("hello", options={"temperature": 0}) == "local response"
    assert client.calls == [{
        "model": "qwen2.5:0.5b",
        "messages": [{"role": "user", "content": "hello"}],
        "options": {"temperature": 0},
    }]


def test_ollama_client_is_created_lazily(monkeypatch):
    client = FakeOllamaClient({"message": {"content": "generated"}})
    created = []

    module = ModuleType("ollama")

    def create_client(*, host):
        created.append(host)
        return client

    module.Client = create_client
    monkeypatch.setitem(__import__("sys").modules, "ollama", module)
    provider = OllamaProvider(host="http://localhost:11434")

    assert created == []
    assert provider.generate("hello") == "generated"
    assert created == ["http://localhost:11434"]


def test_ollama_non_text_response_is_rejected():
    provider = OllamaProvider(client=FakeOllamaClient({"message": {"content": 42}}))

    with pytest.raises(RuntimeError, match="non-text response"):
        provider.generate("hello")


def test_ollama_errors_are_wrapped_with_cause():
    cause = ConnectionError("connection details")

    class FailingClient:
        def chat(self, **_request):
            raise cause

    provider = OllamaProvider(client=FailingClient())

    with pytest.raises(RuntimeError, match="Ollama generation failed") as exc_info:
        provider.generate("hello")

    assert exc_info.value.__cause__ is cause
    assert "connection details" not in str(exc_info.value)
