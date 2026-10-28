"""Configuration loading and validation for the experimental QLoRA path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "finetuning.yaml"


def load_finetuning_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    validate_finetuning_config(config)
    config["_config_path"] = str(config_path)
    return config


def validate_finetuning_config(config: Any) -> None:
    if not isinstance(config, dict):
        raise ValueError("Fine-tuning configuration must be a YAML mapping.")

    required_sections = {
        "model": ("base_model", "smoke_model"),
        "dataset": ("directory",),
        "evaluation": ("baseline_path",),
        "output": ("directory", "experiment_name"),
        "quantization": ("load_in_4bit", "compute_dtype", "quant_type", "use_double_quant"),
        "training": (
            "max_sequence_length", "per_device_train_batch_size",
            "gradient_accumulation_steps", "epochs", "learning_rate",
            "optimizer", "gradient_checkpointing", "fp16", "bf16",
            "logging_steps", "eval_strategy", "save_strategy", "seed",
        ),
        "lora": ("r", "alpha", "dropout", "target_modules"),
        "inference": ("load_in_4bit", "compute_dtype", "quant_type", "use_double_quant"),
        "generation": ("max_new_tokens", "do_sample", "seed"),
        "smoke": ("max_steps", "train_examples"),
    }
    for section, keys in required_sections.items():
        values = config.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"Fine-tuning configuration section '{section}' is required.")
        missing = [key for key in keys if key not in values]
        if missing:
            raise ValueError(
                f"Fine-tuning configuration section '{section}' is missing: "
                + ", ".join(missing)
            )

    for section, key in (
        ("model", "base_model"),
        ("model", "smoke_model"),
        ("dataset", "directory"),
        ("output", "directory"),
        ("output", "experiment_name"),
    ):
        value = config[section][key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Fine-tuning configuration '{section}.{key}' must be non-empty.")

    training = config["training"]
    for key in (
        "max_sequence_length", "per_device_train_batch_size",
        "gradient_accumulation_steps", "epochs", "logging_steps", "seed",
    ):
        if not isinstance(training[key], int) or training[key] <= 0:
            raise ValueError(f"Fine-tuning setting training.{key} must be a positive integer.")
    if training["fp16"] and training["bf16"]:
        raise ValueError("Fine-tuning cannot enable fp16 and bf16 at the same time.")
    compute_dtype = config["quantization"]["compute_dtype"]
    if compute_dtype not in {"float16", "bfloat16", "float32"}:
        raise ValueError("quantization.compute_dtype must be float16, bfloat16, or float32.")
    if config["inference"]["compute_dtype"] not in {"float16", "bfloat16", "float32"}:
        raise ValueError("inference.compute_dtype must be float16, bfloat16, or float32.")
    if training["bf16"] and compute_dtype != "bfloat16":
        raise ValueError("bf16 training requires quantization.compute_dtype: bfloat16.")
    if training["fp16"] and compute_dtype != "float16":
        raise ValueError("fp16 training requires quantization.compute_dtype: float16.")
    if training["learning_rate"] <= 0:
        raise ValueError("Fine-tuning setting training.learning_rate must be positive.")
    if training["eval_strategy"] not in {"steps", "epoch"}:
        raise ValueError("training.eval_strategy must be steps or epoch so validation is used.")
    if training["save_strategy"] not in {"steps", "epoch"}:
        raise ValueError("training.save_strategy must be one of: steps, epoch.")
    if training["eval_strategy"] != training["save_strategy"]:
        raise ValueError(
            "Evaluation and save strategies must match when best-model loading is enabled."
        )
    if training["eval_strategy"] == "steps" and (
        not isinstance(training.get("eval_steps"), int) or training["eval_steps"] <= 0
    ):
        raise ValueError("training.eval_steps must be positive when eval_strategy is steps.")
    if training["save_strategy"] == "steps" and (
        not isinstance(training.get("save_steps"), int) or training["save_steps"] <= 0
    ):
        raise ValueError("training.save_steps must be positive when save_strategy is steps.")

    lora = config["lora"]
    if not isinstance(lora["r"], int) or lora["r"] <= 0:
        raise ValueError("lora.r must be a positive integer.")
    if not isinstance(lora["alpha"], int) or lora["alpha"] <= 0:
        raise ValueError("lora.alpha must be a positive integer.")
    if not 0 <= float(lora["dropout"]) < 1:
        raise ValueError("lora.dropout must be in the range [0, 1).")
    if not isinstance(lora["target_modules"], list) or not lora["target_modules"]:
        raise ValueError("lora.target_modules must be a non-empty list.")
    if any(not isinstance(module, str) or not module for module in lora["target_modules"]):
        raise ValueError("Every lora.target_modules entry must be a non-empty string.")

    smoke = config["smoke"]
    if not isinstance(smoke["max_steps"], int) or smoke["max_steps"] <= 0:
        raise ValueError("smoke.max_steps must be a positive integer.")
    if not isinstance(smoke["train_examples"], int) or smoke["train_examples"] <= 0:
        raise ValueError("smoke.train_examples must be a positive integer.")


def resolve_config_path(value: str | Path, config: dict[str, Any]) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    config_path = Path(config["_config_path"])
    project_root = config_path.parent.parent
    return (project_root / path).resolve()


def resolve_run_settings(
    config: dict[str, Any],
    *,
    model_override: str | None = None,
    smoke: bool = False,
) -> dict[str, Any]:
    validate_finetuning_config(config)
    model_name = model_override or (
        config["model"]["smoke_model"] if smoke else config["model"]["base_model"]
    )
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("The selected fine-tuning model must be a non-empty model identifier.")
    settings = {
        "model_name": model_name,
        "smoke": smoke,
        "max_steps": config["smoke"]["max_steps"] if smoke else -1,
        "train_examples": config["smoke"]["train_examples"] if smoke else None,
    }
    settings["adapter_path"] = resolve_config_path(
        config["output"]["directory"], config
    ) / (
        config["output"].get(
            "smoke_experiment_name",
            f"{config['output']['experiment_name']}-smoke",
        )
        if smoke else config["output"]["experiment_name"]
    )
    return settings
