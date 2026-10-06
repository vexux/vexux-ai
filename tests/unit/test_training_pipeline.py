from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from datasets import Dataset

from data.formatter import DatasetFormatter
from data.loader import DatasetLoader
from lora import manager as lora_manager
from models.providers.qwen import QwenProvider
from training import evaluate as training_evaluate
from training import factory as training_factory
from training import train as training_entry
from training.configuration import (
    DEFAULT_CONFIG_PATH,
    load_finetuning_config,
    resolve_run_settings,
    validate_finetuning_config,
)
from training.inference import InferencePipeline


@pytest.fixture
def config():
    return load_finetuning_config()


def test_finetuning_config_is_separate_and_uses_laptop_safe_primary_defaults(config):
    assert config["model"]["base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert config["model"]["smoke_model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert config["training"]["per_device_train_batch_size"] == 1
    assert config["training"]["gradient_accumulation_steps"] == 8
    assert config["training"]["max_sequence_length"] == 256
    assert config["training"]["gradient_checkpointing"] is True
    assert config["training"]["fp16"] is False
    assert config["training"]["bf16"] is True
    assert config["quantization"]["load_in_4bit"] is True
    assert config["quantization"]["quant_type"] == "nf4"
    assert Path(config["_config_path"]) == DEFAULT_CONFIG_PATH


def test_smoke_settings_select_small_model_one_step_and_separate_artifact(config):
    settings = resolve_run_settings(config, smoke=True)

    assert settings["model_name"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert settings["max_steps"] == 1
    assert settings["adapter_path"].name == "qwen25-05b-smoke"
    assert resolve_run_settings(config)["model_name"] == "Qwen/Qwen2.5-1.5B-Instruct"


def test_invalid_smoke_configuration_is_rejected(config):
    config["smoke"]["max_steps"] = 0

    with pytest.raises(ValueError, match="smoke.max_steps"):
        validate_finetuning_config(config)


def test_finetuning_requires_validation_evaluation(config):
    config["training"]["eval_strategy"] = "no"

    with pytest.raises(ValueError, match="so validation is used"):
        validate_finetuning_config(config)


def test_dataset_loader_reads_all_explicit_split_files(tmp_path):
    rows = {
        "train": ['{"instruction":"train","input":"","output":"ok"}\n'],
        "validation": ['{"instruction":"validation","input":"","output":"ok"}\n'],
        "test": ['{"instruction":"test","input":"","output":"ok"}\n'],
    }
    for split, contents in rows.items():
        (tmp_path / f"{split}.jsonl").write_text("".join(contents), encoding="utf-8")

    dataset = DatasetLoader(str(tmp_path)).load()

    assert set(dataset.keys()) == {"train", "validation", "test"}
    assert [len(dataset[name]) for name in ("train", "validation", "test")] == [1, 1, 1]


def test_dataset_loader_and_formatter_preserve_conversational_fraud_records(tmp_path):
    example = {
        "category": "shared_device",
        "messages": [
            {"role": "user", "content": "What can a shared device indicate?"},
            {"role": "assistant", "content": "It is a signal that needs context."},
        ],
    }
    for split in ("train", "validation", "test"):
        (tmp_path / f"{split}.jsonl").write_text(
            json.dumps(example) + "\n",
            encoding="utf-8",
        )

    loaded = DatasetLoader(str(tmp_path)).load()
    formatted = DatasetFormatter.format(loaded["train"])

    assert formatted.column_names == ["messages"]
    assert formatted[0]["messages"] == example["messages"]


def test_dataset_loader_reports_missing_split(tmp_path):
    (tmp_path / "train.jsonl").write_text(
        '{"instruction":"train","input":"","output":"ok"}\n',
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="validation.jsonl"):
        DatasetLoader(str(tmp_path)).load()


def test_dataset_loader_validates_held_out_test_rows(tmp_path):
    rows = {
        "train": '{"instruction":"train","input":"","output":"ok"}\n',
        "validation": '{"instruction":"validation","input":"","output":"ok"}\n',
        "test": '{"instruction":"test","input":"","output":""}\n',
    }
    for split, content in rows.items():
        (tmp_path / f"{split}.jsonl").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="test example 0"):
        DatasetLoader(str(tmp_path)).load()


def test_formatter_emits_conversational_messages_and_rejects_invalid_examples():
    dataset = Dataset.from_list([
        {"instruction": "Summarize", "input": "A short text.", "output": "Summary."},
    ])

    formatted = DatasetFormatter.format(dataset)

    assert formatted.column_names == ["messages"]
    assert formatted[0]["messages"] == [
        {"role": "user", "content": "Summarize\n\nA short text."},
        {"role": "assistant", "content": "Summary."},
    ]
    with pytest.raises(ValueError, match="instruction"):
        DatasetFormatter.format(Dataset.from_list([
            {"instruction": "", "input": "", "output": "answer"},
        ]))


def test_trainer_factory_passes_validation_and_reproducible_memory_settings(
    config, monkeypatch
):
    config = copy.deepcopy(config)
    config["training"]["output_dir"] = "temporary-trainer-output"
    captured_config = {}
    captured_trainer = {}

    def fake_config(**kwargs):
        captured_config.update(kwargs)
        return kwargs

    def fake_trainer(**kwargs):
        captured_trainer.update(kwargs)
        return SimpleNamespace(model=kwargs["model"])

    monkeypatch.setattr(training_factory, "SFTConfig", fake_config)
    monkeypatch.setattr(training_factory, "SFTTrainer", fake_trainer)
    train_dataset = object()
    validation_dataset = object()

    training_factory.TrainerFactory.create(
        model=object(),
        tokenizer=object(),
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        config=config,
        peft_config="lora-config",
    )

    assert captured_trainer["train_dataset"] is train_dataset
    assert captured_trainer["eval_dataset"] is validation_dataset
    assert captured_trainer["peft_config"] == "lora-config"
    assert captured_config["eval_strategy"] == "epoch"
    assert captured_config["max_length"] == 256
    assert captured_config["gradient_checkpointing"] is True
    assert captured_config["optim"] == "paged_adamw_8bit"
    assert captured_config["seed"] == captured_config["data_seed"] == 42


def test_lora_manager_builds_config_and_rejects_missing_target_modules(config, monkeypatch):
    captured = {}

    class FakeModel:
        def named_modules(self):
            return [("", self), ("model.layers.0.self_attn.q_proj", object())]

    monkeypatch.setattr(
        lora_manager,
        "LoraConfig",
        lambda **kwargs: captured.setdefault("lora_config", kwargs),
    )
    config = copy.deepcopy(config)
    config["lora"]["target_modules"] = ["q_proj"]
    model = FakeModel()

    assert lora_manager.LoRAManager.create_config(model, config) == captured["lora_config"]
    assert captured["lora_config"]["r"] == 16
    assert captured["lora_config"]["target_modules"] == ["q_proj"]

    config["lora"]["target_modules"] = ["missing_proj"]
    with pytest.raises(ValueError, match="missing_proj"):
        lora_manager.LoRAManager.create_config(model, config)


def test_run_training_passes_train_and_validation_but_not_test_and_writes_manifest(
    config, tmp_path, monkeypatch
):
    config = copy.deepcopy(config)
    config["output"]["directory"] = str(tmp_path / "artifacts")
    split_dataset = {
        name: Dataset.from_list([
            {"instruction": f"{name}-{index}", "input": "", "output": "ok"}
            for index in range(size)
        ])
        for name, size in (("train", 3), ("validation", 2), ("test", 1))
    }
    monkeypatch.setattr(
        training_entry,
        "DatasetLoader",
        lambda _path: SimpleNamespace(load=lambda: split_dataset),
    )
    monkeypatch.setattr(
        training_entry,
        "TrainingModelLoader",
        SimpleNamespace(load=lambda model_name, _config: (
            SimpleNamespace(config=SimpleNamespace(), print_trainable_parameters=lambda: None),
            SimpleNamespace(save_pretrained=lambda _path: None),
        )),
    )
    monkeypatch.setattr(
        training_entry.LoRAManager,
        "create_config",
        lambda model, _config: "peft-config",
    )
    captured = {}

    class FakeTrainer:
        state = SimpleNamespace(log_history=[
            {"eval_loss": 0.25},
            {"loss": 0.5},
        ])

        def train(self):
            return SimpleNamespace(metrics={"train_loss": 0.5})

        def save_model(self, path):
            captured["saved_adapter"] = path

    def create_trainer(**kwargs):
        captured.update(kwargs)
        captured["train_dataset"] = kwargs["train_dataset"]
        captured["validation_dataset"] = kwargs["validation_dataset"]
        return FakeTrainer()

    monkeypatch.setattr(training_entry.TrainerFactory, "create", create_trainer)

    manifest = training_entry.run_training(config, smoke=True)
    manifest_path = Path(manifest["output_adapter_path"]) / "manifest.json"

    assert captured["train_dataset"]["messages"][0][0]["content"] == "train-0"
    assert captured["validation_dataset"]["messages"][0][0]["content"] == "validation-0"
    assert len(captured["train_dataset"]) == 2
    assert len(captured["validation_dataset"]) == 2
    assert "test_dataset" not in captured
    assert manifest["dataset_split_counts"] == {
        "train": 3, "validation": 2, "test": 1,
    }
    assert manifest["final_training_loss"] == 0.5
    assert manifest["final_validation_metrics"] == {"eval_loss": 0.25}
    assert manifest_path.is_file()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["smoke_test"] is True
    assert captured["max_steps"] == 1
    assert captured["peft_config"] == "peft-config"


def test_inference_pipeline_parameterizes_base_adapter_and_quantization(
    config, tmp_path
):
    config = copy.deepcopy(config)
    config["output"]["directory"] = str(tmp_path)
    adapter = tmp_path / "adapter-qwen-15b"
    adapter.mkdir()
    calls = []

    class FakeProvider:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def generate(self, prompt, **kwargs):
            return f"{prompt}:{kwargs['max_new_tokens']}"

    pipeline = InferencePipeline(
        config_path=config["_config_path"],
        model_name="Qwen/Qwen2.5-1.5B-Instruct",
        adapter_path=adapter,
        provider_factory=FakeProvider,
    )

    assert calls[0]["model_name"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert calls[0]["adapter_path"] == str(adapter)
    assert calls[0]["load_in_4bit"] is True
    assert pipeline.generate("prompt") == "prompt:200"

    base_pipeline = InferencePipeline(
        config_path=config["_config_path"],
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        load_adapter=False,
        provider_factory=FakeProvider,
    )
    assert calls[1]["model_name"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert calls[1]["adapter_path"] is None


def test_inference_requires_configured_adapter_directory(config):
    with pytest.raises(FileNotFoundError, match="adapter directory"):
        InferencePipeline(
            config_path=config["_config_path"],
            adapter_path=Path("missing-adapter-directory"),
        )


def test_qwen_provider_configures_optional_4bit_adapter_inference(monkeypatch):
    calls = {}

    class FakeTokenizer:
        eos_token = "</s>"
        pad_token = None

        @classmethod
        def from_pretrained(cls, model_name):
            calls["tokenizer_model"] = model_name
            return cls()

    class FakeModel:
        generation_config = SimpleNamespace()

        def eval(self):
            return self

    class FakeModelLoader:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["model"] = (model_name, kwargs)
            return FakeModel()

    class FakeBitsAndBytesConfig:
        def __init__(self, **kwargs):
            calls["quantization"] = kwargs

    fake_transformers = ModuleType("transformers")
    fake_transformers.AutoTokenizer = FakeTokenizer
    fake_transformers.AutoModelForCausalLM = FakeModelLoader
    fake_transformers.BitsAndBytesConfig = FakeBitsAndBytesConfig
    fake_peft = ModuleType("peft")
    class FakePeftModel:
        @staticmethod
        def from_pretrained(model, adapter_path):
            calls["adapter"] = adapter_path
            return model

    fake_peft.PeftModel = FakePeftModel
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    provider = QwenProvider(
        "Qwen/Qwen2.5-1.5B-Instruct",
        "models/checkpoints/example",
        load_in_4bit=True,
        compute_dtype="bfloat16",
    )

    assert calls["model"][0] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert calls["model"][1]["quantization_config"] is not None
    assert calls["quantization"]["load_in_4bit"] is True
    assert calls["quantization"]["bnb_4bit_quant_type"] == "nf4"
    assert provider.adapter_path == "models/checkpoints/example"


def test_evaluation_captures_base_and_adapter_on_same_test_examples(
    config, tmp_path, monkeypatch
):
    config = copy.deepcopy(config)
    cases = [
        {
            "category": "authority_boundary",
            "prompt": "test one",
            "expected_properties": ["no invention"],
        },
        {
            "category": "general_retention",
            "prompt": "test two",
            "expected_properties": ["concise"],
        },
    ]
    baseline_path = tmp_path / "baseline.jsonl"
    baseline_path.write_text(
        "\n".join(json.dumps(case) for case in cases) + "\n",
        encoding="utf-8",
    )
    config["evaluation"]["baseline_path"] = str(baseline_path)
    monkeypatch.setattr(training_evaluate, "load_finetuning_config", lambda _path: config)
    instances = []

    class FakeInference:
        def __init__(self, _config_path, *, load_adapter):
            self.mode = "adapter" if load_adapter else "base"
            instances.append(self.mode)

        def generate(self, prompt, **kwargs):
            assert kwargs["do_sample"] is False
            return f"{self.mode}:{prompt}"

    destination = tmp_path / "evaluation.json"
    result = training_evaluate.evaluate_base_vs_adapter(
        config["_config_path"],
        output_path=destination,
        inference_factory=FakeInference,
    )

    assert instances == ["base", "adapter"]
    assert result["test_example_count"] == 2
    assert result["evaluation_categories"] == ["authority_boundary", "general_retention"]
    assert result["results"][1]["prompt"] == "test two"
    assert result["results"][1]["base_output"] == "base:test two"
    assert result["results"][1]["adapter_output"] == "adapter:test two"
    assert json.loads(destination.read_text(encoding="utf-8"))["test_example_count"] == 2
