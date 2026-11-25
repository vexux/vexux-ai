from contextlib import nullcontext
from types import ModuleType

import pytest

from core.model_gateway.gateway import ModelGateway
from models.providers.qwen3 import Qwen3Provider


class FakeTensor:
    def __init__(self, values):
        self.values = values
        self.shape = (1, len(values))

    def to(self, device):
        assert device == "cpu"
        return self

    def __getitem__(self, index):
        row, column = index
        return self.values[row:][column]


class FakeTokenizer:
    pad_token_id = 0
    truncation_side = "right"

    def __init__(self):
        self.chat_calls = []
        self.tokenize_calls = []
        self.decoded = None

    def apply_chat_template(self, messages, **kwargs):
        self.chat_calls.append((messages, kwargs))
        return "formatted-chat"

    def __call__(self, text, **kwargs):
        self.tokenize_calls.append((text, kwargs))
        return {
            "input_ids": FakeTensor([1, 2, 3]),
            "attention_mask": FakeTensor([1, 1, 1]),
        }

    def decode(self, tokens, **kwargs):
        self.decoded = (tokens, kwargs)
        return "generated-only answer"


class FakeModel:
    def __init__(self, failure=None):
        self.failure = failure
        self.generate_kwargs = None
        self.device = None
        self.evaluated = False

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.evaluated = True

    def generate(self, **kwargs):
        if self.failure:
            raise self.failure
        self.generate_kwargs = kwargs
        return FakeTensor([1, 2, 3, 8, 9])


def create_local_snapshot(tmp_path, name):
    model_path = tmp_path / name
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_path / "model.safetensors").write_bytes(b"mock weights")
    return model_path


def install_transformers_mocks(
    monkeypatch,
    tokenizer=None,
    model=None,
    *,
    tokenizer_failures=None,
    model_failures=None,
    model_factories=None,
):
    tokenizer = tokenizer or FakeTokenizer()
    model = model or FakeModel()
    calls = {"tokenizer": [], "model": []}
    tokenizer_failures = tokenizer_failures or {}
    model_failures = model_failures or {}
    model_factories = model_factories or {}

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["tokenizer"].append((path, kwargs))
            assert kwargs["local_files_only"] is True
            if path in tokenizer_failures:
                raise tokenizer_failures[path]
            return tokenizer

    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["model"].append((path, kwargs))
            assert kwargs["local_files_only"] is True
            if path in model_failures:
                raise model_failures[path]
            if path in model_factories:
                return model_factories[path]()
            return model

    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = AutoTokenizer
    transformers.AutoModelForCausalLM = AutoModelForCausalLM
    torch = ModuleType("torch")
    torch.bfloat16 = "mock-bfloat16"
    torch.inference_mode = nullcontext
    monkeypatch.setitem(__import__("sys").modules, "transformers", transformers)
    monkeypatch.setitem(__import__("sys").modules, "torch", torch)
    return tokenizer, model, calls


def test_qwen3_loads_lazily_once_with_local_cpu_settings_and_decodes_new_tokens(
    monkeypatch, tmp_path
):
    model_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-4B")
    fallback_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    tokenizer, model, calls = install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(
        model_path,
        fallback_model_path=fallback_path,
        max_input_tokens=32,
        max_new_tokens=8,
    )

    assert calls == {"tokenizer": [], "model": []}
    assert provider.generate("Hello", max_new_tokens=99) == "generated-only answer"
    assert provider.generate("Again") == "generated-only answer"

    assert len(calls["tokenizer"]) == 1
    assert calls["tokenizer"][0] == (
        str(model_path),
        {"local_files_only": True},
    )
    assert calls["model"][0][1] == {
        "local_files_only": True,
        "dtype": "mock-bfloat16",
    }
    assert model.device == "cpu"
    assert model.evaluated is True
    assert tokenizer.truncation_side == "left"
    assert tokenizer.chat_calls[0][1] == {
        "tokenize": False,
        "add_generation_prompt": True,
        "enable_thinking": False,
    }
    assert tokenizer.tokenize_calls[0][1] == {
        "return_tensors": "pt",
        "truncation": True,
        "max_length": 32,
    }
    assert model.generate_kwargs["max_new_tokens"] == 8
    assert model.generate_kwargs["do_sample"] is False
    assert tokenizer.decoded == (
        [8, 9],
        {"skip_special_tokens": True},
    )
    assert calls["tokenizer"] == [(str(model_path), {"local_files_only": True})]
    assert provider.metadata == {
        "provider": "qwen3",
        "model": "Qwen3-4B",
        "model_selection": "primary",
        "runtime_mode": "local",
    }


def test_qwen3_provider_defaults_are_4b_and_memory_conservative():
    from pathlib import Path

    provider = Qwen3Provider()

    assert provider.model_path == (
        Path.home()
        / ".cache"
        / "modelscope"
        / "models"
        / "Qwen--Qwen3-4B"
        / "snapshots"
        / "master"
    )
    assert provider.fallback_model_path == (
        Path.home()
        / ".cache"
        / "modelscope"
        / "models"
        / "Qwen--Qwen3-0.6B"
        / "snapshots"
        / "master"
    )
    assert provider.max_input_tokens == 1024
    assert provider.max_new_tokens == 128


def test_qwen3_falls_back_when_primary_path_is_missing(monkeypatch, tmp_path, caplog):
    fallback_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(
        tmp_path / "missing-primary",
        fallback_model_path=fallback_path,
    )

    gateway = ModelGateway(provider)
    assert gateway.generate("Hello") == "generated-only answer"
    assert provider.metadata["model"] == "Qwen3-0.6B"
    assert provider.metadata["model_selection"] == "fallback"
    assert gateway.provider_metadata()["model"] == "Qwen3-0.6B"
    assert gateway.provider_metadata()["model_selection"] == "fallback"
    assert "Primary local Qwen3 model missing-primary failed" in caplog.text
    assert "attempting configured fallback Qwen3-0.6B" in caplog.text


def test_qwen3_falls_back_when_primary_initialization_raises(monkeypatch, tmp_path):
    primary_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-4B")
    fallback_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    install_transformers_mocks(
        monkeypatch,
        model_failures={str(primary_path): OSError("private path omitted")},
    )
    provider = Qwen3Provider(
        primary_path,
        fallback_model_path=fallback_path,
    )

    assert provider.generate("Hello") == "generated-only answer"
    assert provider.metadata["model"] == "Qwen3-0.6B"
    assert provider.metadata["model_selection"] == "fallback"


def test_qwen3_releases_partial_primary_model_before_fallback(
    monkeypatch, tmp_path
):
    import weakref

    primary_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-4B")
    fallback_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    partial_model_ref = []

    class FailingMoveModel(FakeModel):
        def to(self, device):
            raise OSError("CPU placement failed")

    def create_partial_model():
        partial_model = FailingMoveModel()
        partial_model_ref.append(weakref.ref(partial_model))
        return partial_model

    def create_fallback_model():
        assert partial_model_ref[0]() is None
        return FakeModel()

    install_transformers_mocks(
        monkeypatch,
        model_factories={
            str(primary_path): create_partial_model,
            str(fallback_path): create_fallback_model,
        },
    )
    provider = Qwen3Provider(
        primary_path,
        fallback_model_path=fallback_path,
    )

    assert provider.generate("Hello") == "generated-only answer"
    assert provider.metadata["model_selection"] == "fallback"


def test_qwen3_both_fail_with_both_safe_failure_reasons(monkeypatch, tmp_path):
    primary_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-4B")
    fallback_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    _, _, calls = install_transformers_mocks(
        monkeypatch,
        model_failures={
            str(primary_path): ValueError("private path must not be reported"),
            str(fallback_path): OSError("private path must not be reported"),
        },
    )
    provider = Qwen3Provider(
        primary_path,
        fallback_model_path=fallback_path,
    )

    with pytest.raises(RuntimeError) as error:
        provider.generate("Hello")

    assert "Primary Qwen3-4B failed: model configuration or weights were rejected" in str(error.value)
    assert "Fallback Qwen3-0.6B failed: local model or runtime I/O failed" in str(error.value)
    assert "private path" not in str(error.value)
    assert str(primary_path) not in str(error.value)
    assert str(fallback_path) not in str(error.value)
    calls_after_failure = {
        key: list(value)
        for key, value in calls.items()
    }
    with pytest.raises(RuntimeError, match="Could not load either local Qwen3 model"):
        provider.generate("Try again")
    assert calls == calls_after_failure


def test_qwen3_formats_json_and_supports_chat_templates_without_thinking_option(
    monkeypatch, tmp_path
):
    tokenizer = FakeTokenizer()

    def legacy_template(messages, *, tokenize, add_generation_prompt):
        tokenizer.chat_calls.append(
            (messages, {"tokenize": tokenize, "add_generation_prompt": add_generation_prompt})
        )
        return "legacy-chat"

    tokenizer.apply_chat_template = legacy_template
    model_path = create_local_snapshot(tmp_path, "qwen3")
    _, model, _ = install_transformers_mocks(monkeypatch, tokenizer=tokenizer)
    provider = Qwen3Provider(model_path, max_new_tokens=12)

    provider.generate("Return an object", response_format="json")

    assert tokenizer.chat_calls[0] == (
        [
            {
                "role": "user",
                "content": (
                    "Return an object\n\n"
                    "Respond with valid JSON only. Do not include Markdown or commentary."
                ),
            }
        ],
        {"tokenize": False, "add_generation_prompt": True},
    )
    assert model.generate_kwargs["max_new_tokens"] == 12


def test_qwen3_06b_remains_available_as_explicit_primary(monkeypatch, tmp_path):
    small_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-0.6B")
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(small_path, fallback_model_path=tmp_path / "unused")

    assert provider.generate("Hello") == "generated-only answer"
    assert provider.metadata["model"] == "Qwen3-0.6B"
    assert provider.metadata["model_selection"] == "primary"


def test_qwen3_reports_both_loading_errors_and_generation_errors(monkeypatch, tmp_path):
    primary_path = tmp_path / "missing-primary"
    fallback_path = tmp_path / "missing-fallback"
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(
        primary_path,
        fallback_model_path=fallback_path,
    )
    with pytest.raises(RuntimeError, match="Could not load either local Qwen3 model") as loading:
        provider.generate("Hello")
    assert "Primary missing-primary failed" in str(loading.value)
    assert "Fallback missing-fallback failed" in str(loading.value)
    assert loading.value.__cause__ is None

    model_path = create_local_snapshot(tmp_path, "generation-fails")
    generation_model = FakeModel(failure=ValueError("generation rejected"))
    install_transformers_mocks(monkeypatch, model=generation_model)
    provider = Qwen3Provider(model_path)
    with pytest.raises(RuntimeError, match="Qwen3 generation failed") as generation:
        provider.generate("Hello")
    assert isinstance(generation.value.__cause__, ValueError)


def test_qwen3_gateway_metadata_and_input_validation(monkeypatch, tmp_path):
    model_path = create_local_snapshot(tmp_path, "Qwen--Qwen3-4B")
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(model_path)
    gateway = ModelGateway(provider)

    assert gateway.provider_metadata() == {
        "provider": "qwen3",
        "model": "Qwen3-4B",
        "model_selection": "not_loaded",
        "runtime_mode": "local",
    }
    with pytest.raises(ValueError, match="non-empty"):
        gateway.generate(" ")
    with pytest.raises(ValueError, match="response format"):
        gateway.generate("Hello", response_format="xml")
    gateway.generate("Hello")
    assert gateway.provider_metadata()["model"] == "Qwen3-4B"
    assert gateway.provider_metadata()["model_selection"] == "primary"


def test_qwen3_validates_required_local_files_before_runtime_load(monkeypatch, tmp_path):
    invalid_path = tmp_path / "incomplete"
    invalid_path.mkdir()
    fallback_path = create_local_snapshot(tmp_path, "fallback")
    _, _, calls = install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(invalid_path, fallback_model_path=fallback_path)

    provider.generate("Hello")

    assert calls["tokenizer"] == [(str(fallback_path), {"local_files_only": True})]


def test_qwen3_validates_all_indexed_model_shards_before_runtime_load(
    monkeypatch, tmp_path
):
    primary_path = tmp_path / "incomplete-shards"
    primary_path.mkdir()
    (primary_path / "config.json").write_text("{}", encoding="utf-8")
    (primary_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (primary_path / "model.safetensors.index.json").write_text(
        '{"weight_map":{"layer.weight":"model-00001-of-00002.safetensors"}}',
        encoding="utf-8",
    )
    fallback_path = create_local_snapshot(tmp_path, "fallback")
    _, _, calls = install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(primary_path, fallback_model_path=fallback_path)

    provider.generate("Hello")

    assert calls["tokenizer"] == [(str(fallback_path), {"local_files_only": True})]


def test_qwen3_expands_environment_variables_in_model_path(monkeypatch):
    monkeypatch.setenv("VEXUX_QWEN3_CACHE", "C:/local/qwen3")

    provider = Qwen3Provider("%VEXUX_QWEN3_CACHE%")

    assert str(provider.model_path) == "C:\\local\\qwen3"
