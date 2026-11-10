from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time
from types import ModuleType

import pytest

from core.model_gateway.gateway import ModelGateway
from models.providers.llama_cpp import LlamaCppProvider


class MockLlama:
    def __init__(self, *, response=None, **kwargs):
        self.init_kwargs = kwargs
        self.response = response or {
            "choices": [{"message": {"content": "local response"}}]
        }
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def install_llama_mock(monkeypatch, response=None, delay=0):
    module = ModuleType("llama_cpp")
    instances = []
    lock = threading.Lock()

    def create_model(**kwargs):
        if delay:
            time.sleep(delay)
        model = MockLlama(response=response, **kwargs)
        with lock:
            instances.append(model)
        return model

    module.Llama = create_model
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    return instances


def model_file(tmp_path: Path) -> Path:
    path = tmp_path / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    path.write_bytes(b"mock gguf")
    return path


def test_llama_provider_loads_lazily_on_cpu_and_uses_bounded_deterministic_generation(
    monkeypatch, tmp_path
):
    instances = install_llama_mock(monkeypatch)
    provider = LlamaCppProvider(
        model_file(tmp_path),
        n_ctx=1024,
        n_threads=3,
        max_new_tokens=64,
    )
    assert instances == []

    assert provider.generate("Hello", max_new_tokens=128) == "local response"

    assert len(instances) == 1
    assert instances[0].init_kwargs == {
        "model_path": str(model_file(tmp_path)),
        "n_ctx": 1024,
        "n_threads": 3,
        "n_gpu_layers": 0,
        "verbose": False,
    }
    request = instances[0].calls[0]
    assert request["messages"] == [{"role": "user", "content": "Hello"}]
    assert request["max_tokens"] == 64
    assert request["temperature"] == 0.0
    assert request["top_p"] == 1.0


def test_llama_provider_validates_local_path_and_missing_dependency_without_fallback(
    monkeypatch, tmp_path
):
    provider = LlamaCppProvider(tmp_path / "missing.gguf")
    with pytest.raises(FileNotFoundError, match="Local GGUF model file does not exist"):
        provider.generate("Hello")

    model_path = model_file(tmp_path)
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    missing_package = LlamaCppProvider(model_path)
    with pytest.raises(RuntimeError, match="requires the optional 'llama-cpp-python'") as error:
        missing_package.generate("Hello")
    assert isinstance(error.value.__cause__, ImportError)
    assert missing_package.name == "llama_cpp"


def test_llama_provider_adds_json_guidance_and_maps_max_token_alias(
    monkeypatch, tmp_path
):
    instances = install_llama_mock(monkeypatch)
    provider = LlamaCppProvider(model_file(tmp_path), max_new_tokens=32)

    provider.generate("Give an object", response_format="json", max_tokens=8)

    request = instances[0].calls[0]
    assert "Respond with valid JSON only" in request["messages"][0]["content"]
    assert request["max_tokens"] == 8
    assert request["temperature"] == 0.0


def test_llama_provider_surfaces_generation_errors_without_fallback(
    monkeypatch, tmp_path
):
    module = ModuleType("llama_cpp")

    class FailingLlama:
        def __init__(self, **_kwargs):
            pass

        def create_chat_completion(self, **_kwargs):
            raise OSError("local runtime failed")

    module.Llama = FailingLlama
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    provider = LlamaCppProvider(model_file(tmp_path))

    with pytest.raises(RuntimeError, match="generation failed") as error:
        provider.generate("Hello")

    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"n_ctx": 0}, "n_ctx must be a positive integer"),
        ({"n_threads": -1}, "n_threads must be a positive integer"),
        ({"max_new_tokens": 0}, "max_new_tokens must be a positive integer"),
        ({"n_ctx": 9000}, "n_ctx must not exceed 8192"),
    ],
)
def test_llama_provider_rejects_invalid_generation_configuration(
    tmp_path, kwargs, message
):
    with pytest.raises(ValueError, match=message):
        LlamaCppProvider(model_file(tmp_path), **kwargs)


def test_llama_provider_rejects_invalid_prompts_and_output_limits(
    monkeypatch, tmp_path
):
    instances = install_llama_mock(monkeypatch)
    provider = LlamaCppProvider(model_file(tmp_path))

    with pytest.raises(ValueError, match="non-empty"):
        provider.generate(" ")
    with pytest.raises(ValueError, match="response format"):
        provider.generate("Hello", response_format="xml")
    with pytest.raises(ValueError, match="max_new_tokens must be a positive integer"):
        provider.generate("Hello", max_new_tokens=0)
    assert instances == []


def test_llama_provider_lazy_loading_is_thread_safe(monkeypatch, tmp_path):
    instances = install_llama_mock(monkeypatch, delay=0.03)
    provider = LlamaCppProvider(model_file(tmp_path))

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(provider.generate, ["Hello"] * 8))

    assert results == ["local response"] * 8
    assert len(instances) == 1
    assert len(instances[0].calls) == 8


def test_llama_provider_gateway_metadata_does_not_expose_full_path(tmp_path):
    provider = LlamaCppProvider(model_file(tmp_path))
    gateway = ModelGateway(provider)

    assert gateway.provider_metadata() == {
        "provider": "llama_cpp",
        "model": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "runtime_mode": "local",
    }
    assert str(tmp_path) not in str(gateway.provider_metadata())
