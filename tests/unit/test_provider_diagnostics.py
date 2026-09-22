import pytest

from core.config import load_config_from_env, provider_diagnostic
from core.model_gateway.gateway import ModelGateway
from models.providers.fake import FakeProvider
from models.providers.ollama import OllamaProvider


def test_provider_configuration_reads_model_names_from_process_environment(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    config = load_config_from_env()
    assert provider_diagnostic(config) == {
        "provider": "ollama",
        "model": "qwen3:4b",
        "host": config.ollama_host,
        "runtime_mode": "local",
    }


def test_invalid_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "unexpected-remote")
    with pytest.raises(ValueError, match="Unsupported MODEL_PROVIDER"):
        load_config_from_env()


def test_missing_provider_is_rejected(monkeypatch, tmp_path):
    import core.config as config_module

    monkeypatch.setattr(config_module, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="must be explicitly configured"):
        load_config_from_env()


def test_gateway_provider_metadata_contains_no_secret():
    gateway = ModelGateway(FakeProvider("safe-model"))
    metadata = gateway.provider_metadata()
    assert metadata == {
        "provider": "fake",
        "model": "safe-model",
        "runtime_mode": "deterministic",
    }
    assert "key" not in str(metadata).lower()
    assert "password" not in str(metadata).lower()
    assert "token" not in str(metadata).lower()


def test_ollama_provider_metadata_is_explicit():
    provider = OllamaProvider(model_name="qwen3:4b", host="http://localhost:11434")
    assert provider.metadata == {
        "provider": "ollama",
        "model": "qwen3:4b",
        "host": "http://localhost:11434",
        "runtime_mode": "local",
    }
