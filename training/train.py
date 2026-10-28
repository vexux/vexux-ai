"""Canonical entry point for the experimental QLoRA training pipeline."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.formatter import DatasetFormatter
from data.loader import DatasetLoader
from lora.manager import LoRAManager
from training.configuration import (
    DEFAULT_CONFIG_PATH,
    load_finetuning_config,
    resolve_config_path,
    resolve_run_settings,
)
from training.factory import TrainerFactory
from training.model_loader import TrainingModelLoader


def _last_metric(history: list[dict[str, Any]], key: str) -> Any:
    for item in reversed(history):
        if key in item:
            return item[key]
    return None


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _limited(dataset, count: int):
    if len(dataset) < count:
        raise ValueError(
            f"Smoke training requested {count} examples, but the training split "
            f"contains only {len(dataset)}."
        )
    return dataset.select(range(count))


def run_training(
    config: dict[str, Any],
    *,
    model_override: str | None = None,
    smoke: bool = False,
) -> dict[str, Any]:
    settings = resolve_run_settings(config, model_override=model_override, smoke=smoke)
    training_config = copy.deepcopy(config)
    training_config["training"]["output_dir"] = str(settings["adapter_path"])
    if smoke:
        training_config["training"].update({
            "eval_strategy": "steps",
            "eval_steps": 1,
            "save_strategy": "steps",
            "save_steps": 1,
            "logging_steps": 1,
        })

    import torch
    from transformers import set_seed

    seed = training_config["training"]["seed"]
    set_seed(seed)
    data_directory = resolve_config_path(config["dataset"]["directory"], config)
    dataset = DatasetLoader(str(data_directory)).load()
    expected_splits = {"train", "validation", "test"}
    missing_splits = expected_splits - set(dataset.keys())
    if missing_splits:
        raise ValueError(
            "Dataset is missing required splits: " + ", ".join(sorted(missing_splits))
        )
    split_counts = {name: len(dataset[name]) for name in ("train", "validation", "test")}
    if any(count == 0 for count in split_counts.values()):
        raise ValueError("Training, validation, and held-out test splits must all be non-empty.")

    raw_train = dataset["train"]
    if smoke:
        raw_train = _limited(raw_train, settings["train_examples"])
    train_dataset = DatasetFormatter.format(raw_train)
    validation_dataset = DatasetFormatter.format(dataset["validation"])

    started_at = time.perf_counter()
    settings["adapter_path"].mkdir(parents=True, exist_ok=True)
    try:
        model, tokenizer = TrainingModelLoader.load(settings["model_name"], training_config)
        model.config.use_cache = False
        peft_config = LoRAManager.create_config(model, training_config)
        trainer = TrainerFactory.create(
            model=model,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            validation_dataset=validation_dataset,
            config=training_config,
            max_steps=settings["max_steps"],
            peft_config=peft_config,
        )
        training_result = trainer.train()
    except RuntimeError as exc:
        message = str(exc).lower()
        if "out of memory" in message or "cuda oom" in message:
            raise RuntimeError(
                "QLoRA training ran out of CUDA memory. Reduce max_sequence_length "
                "or use the configured 0.5B smoke model."
            ) from exc
        raise

    trainer.save_model(str(settings["adapter_path"]))
    if config["output"].get("save_tokenizer", True):
        tokenizer.save_pretrained(str(settings["adapter_path"]))

    training_metrics = getattr(training_result, "metrics", {}) or {}
    log_history = getattr(getattr(trainer, "state", None), "log_history", []) or []
    validation_metrics = next(
        (
            {key: value for key, value in item.items() if key.startswith("eval_")}
            for item in reversed(log_history)
            if any(key.startswith("eval_") for key in item)
        ),
        {},
    )
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_model": settings["model_name"],
        "dataset_path": str(data_directory),
        "dataset_split_counts": split_counts,
        "train_count": split_counts["train"],
        "validation_count": split_counts["validation"],
        "test_count": split_counts["test"],
        "training_config": {
            key: value for key, value in training_config["training"].items()
            if key != "output_dir"
        },
        "lora_config": dict(training_config["lora"]),
        "quantization_config": dict(training_config["quantization"]),
        "seed": seed,
        "output_adapter_path": str(settings["adapter_path"]),
        "smoke_test": smoke,
        "training_duration_seconds": round(time.perf_counter() - started_at, 3),
        "final_training_loss": training_metrics.get("train_loss")
        if training_metrics.get("train_loss") is not None
        else _last_metric(log_history, "loss"),
        "final_validation_metrics": validation_metrics,
        "training_metrics": training_metrics,
    }
    write_manifest(settings["adapter_path"] / "manifest.json", manifest)
    return manifest


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the experimental QLoRA adapter.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--model",
        help="Override the configured model (the smoke model is selected by default with --smoke).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a one-step QLoRA smoke test using the configured small model.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    config = load_finetuning_config(args.config)
    manifest = run_training(config, model_override=args.model, smoke=args.smoke)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
