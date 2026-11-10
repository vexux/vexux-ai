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


def test_qwen3_configuration_and_diagnostics_are_distinct(monkeypatch, tmp_path):
    import core.config as config_module

    monkeypatch.setattr(config_module, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("MODEL_PROVIDER", "qwen3")
    monkeypatch.setenv("QWEN3_MODEL_PATH", str(tmp_path / "snapshot"))
    monkeypatch.setenv("QWEN3_MAX_INPUT_TOKENS", "512")
    monkeypatch.setenv("QWEN3_MAX_NEW_TOKENS", "64")

    config = load_config_from_env()

    assert config.qwen3_model_path == str(tmp_path / "snapshot")
    assert config.qwen3_max_input_tokens == 512
    assert config.qwen3_max_new_tokens == 64
    assert provider_diagnostic(config) == {
        "provider": "qwen3",
        "runtime_mode": "local",
        "model": "Qwen3-0.6B",
    }


def test_qwen3_generation_limits_are_validated(monkeypatch, tmp_path):
    import core.config as config_module

    monkeypatch.setattr(config_module, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("MODEL_PROVIDER", "qwen3")
    monkeypatch.setenv("QWEN3_MAX_NEW_TOKENS", "0")

    with pytest.raises(ValueError, match="below minimum"):
        load_config_from_env()


def test_llama_cpp_configuration_and_diagnostics_hide_model_directory(
    monkeypatch, tmp_path
):
    import core.config as config_module

    model_path = tmp_path / "private-model-dir" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    monkeypatch.setattr(config_module, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("MODEL_PROVIDER", "llama_cpp")
    monkeypatch.setenv("LLAMA_CPP_MODEL_PATH", str(model_path))
    monkeypatch.setenv("LLAMA_CPP_N_CTX", "1024")
    monkeypatch.setenv("LLAMA_CPP_N_THREADS", "3")
    monkeypatch.setenv("LLAMA_CPP_MAX_NEW_TOKENS", "128")

    config = load_config_from_env()

    assert config.llama_cpp_model_path == str(model_path)
    assert config.llama_cpp_n_ctx == 1024
    assert config.llama_cpp_n_threads == 3
    assert config.llama_cpp_max_new_tokens == 128
    assert provider_diagnostic(config) == {
        "provider": "llama_cpp",
        "runtime_mode": "local",
        "model": model_path.name,
    }
    assert str(tmp_path) not in str(provider_diagnostic(config))
    assert str(tmp_path) not in repr(config)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLAMA_CPP_N_CTX", "0"),
        ("LLAMA_CPP_N_THREADS", "-1"),
        ("LLAMA_CPP_MAX_NEW_TOKENS", "0"),
        ("LLAMA_CPP_N_CTX", "9000"),
        ("LLAMA_CPP_N_THREADS", "17"),
        ("LLAMA_CPP_MAX_NEW_TOKENS", "1025"),
    ],
)
def test_llama_cpp_configuration_rejects_out_of_range_limits(
    monkeypatch, tmp_path, name, value
):
    import core.config as config_module

    monkeypatch.setattr(config_module, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("MODEL_PROVIDER", "llama_cpp")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        load_config_from_env()
