from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

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


def install_transformers_mocks(monkeypatch, tokenizer=None, model=None):
    tokenizer = tokenizer or FakeTokenizer()
    model = model or FakeModel()
    calls = {"tokenizer": [], "model": []}

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["tokenizer"].append((path, kwargs))
            return tokenizer

    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["model"].append((path, kwargs))
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
    monkeypatch,
):
    tokenizer, model, calls = install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider(
        "C:/models/qwen3",
        max_input_tokens=32,
        max_new_tokens=8,
    )

    assert calls == {"tokenizer": [], "model": []}
    assert provider.generate("Hello", max_new_tokens=99) == "generated-only answer"
    assert provider.generate("Again") == "generated-only answer"

    assert len(calls["tokenizer"]) == 1
    assert calls["tokenizer"][0] == (
        "C:\\models\\qwen3",
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


def test_qwen3_formats_json_and_supports_chat_templates_without_thinking_option(
    monkeypatch,
):
    tokenizer = FakeTokenizer()

    def legacy_template(messages, *, tokenize, add_generation_prompt):
        tokenizer.chat_calls.append(
            (messages, {"tokenize": tokenize, "add_generation_prompt": add_generation_prompt})
        )
        return "legacy-chat"

    tokenizer.apply_chat_template = legacy_template
    _, model, _ = install_transformers_mocks(monkeypatch, tokenizer=tokenizer)
    provider = Qwen3Provider("local", max_new_tokens=12)

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


def test_qwen3_reports_loading_and_generation_errors(monkeypatch):
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider("missing-local-snapshot")
    import sys

    transformers = sys.modules["transformers"]

    class MissingTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            assert kwargs["local_files_only"] is True
            raise FileNotFoundError("local files missing")

    transformers.AutoTokenizer = MissingTokenizer
    with pytest.raises(RuntimeError, match="Could not load local Qwen3") as loading:
        provider.generate("Hello")
    assert isinstance(loading.value.__cause__, FileNotFoundError)

    generation_model = FakeModel(failure=ValueError("generation rejected"))
    tokenizer, _, _ = install_transformers_mocks(
        monkeypatch,
        model=generation_model,
    )
    provider = Qwen3Provider("local")
    with pytest.raises(RuntimeError, match="Qwen3 generation failed") as generation:
        provider.generate("Hello")
    assert isinstance(generation.value.__cause__, ValueError)


def test_qwen3_gateway_metadata_and_input_validation(monkeypatch):
    install_transformers_mocks(monkeypatch)
    provider = Qwen3Provider("local")
    gateway = ModelGateway(provider)

    assert gateway.provider_metadata() == {
        "provider": "qwen3",
        "model": "Qwen3-0.6B",
        "runtime_mode": "local",
    }
    with pytest.raises(ValueError, match="non-empty"):
        gateway.generate(" ")
    with pytest.raises(ValueError, match="response format"):
        gateway.generate("Hello", response_format="xml")


def test_qwen3_expands_environment_variables_in_model_path(monkeypatch):
    monkeypatch.setenv("VEXUX_QWEN3_CACHE", "C:/local/qwen3")

    provider = Qwen3Provider("%VEXUX_QWEN3_CACHE%")

    assert str(provider.model_path) == "C:\\local\\qwen3"
