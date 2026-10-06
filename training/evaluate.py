"""Held-out base-versus-adapter output capture for fine-tuning experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from data.loader import DatasetLoader
from training.configuration import (
    DEFAULT_CONFIG_PATH,
    load_finetuning_config,
    resolve_config_path,
)
from training.inference import InferencePipeline


def _prompt(example: dict[str, Any]) -> str:
    instruction = example.get("instruction")
    extra_input = example.get("input", "")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Every held-out test example must have a non-empty instruction.")
    if not isinstance(extra_input, str):
        raise ValueError("Held-out test example input must be a string.")
    return instruction + ("\n\n" + extra_input if extra_input else "")


def evaluate_base_vs_adapter(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    output_path: str | Path | None = None,
    inference_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    config = load_finetuning_config(config_path)
    dataset_path = resolve_config_path(config["dataset"]["directory"], config)
    test_dataset = DatasetLoader(str(dataset_path)).load()["test"]
    if len(test_dataset) == 0:
        raise ValueError("The held-out test split must not be empty.")

    inference_type = inference_factory or InferencePipeline
    generation = dict(config["generation"])
    rows = [
        {
            "index": index,
            "instruction": example["instruction"],
            "input": example.get("input", ""),
            "reference": example["output"],
            "prompt": _prompt(example),
        }
        for index, example in enumerate(test_dataset)
    ]

    outputs: dict[str, list[str]] = {"base": [], "adapter": []}
    for mode in ("base", "adapter"):
        pipeline = inference_type(config_path, load_adapter=(mode == "adapter"))
        try:
            outputs[mode] = [
                pipeline.generate(row["prompt"], **generation)
                for row in rows
            ]
        finally:
            close = getattr(pipeline, "close", None)
            if callable(close):
                close()

    result = {
        "base_model": config["model"]["base_model"],
        "adapter_path": str(
            resolve_config_path(config["output"]["directory"], config)
            / config["output"]["experiment_name"]
        ),
        "dataset_path": str(dataset_path),
        "test_example_count": len(rows),
        "generation_config": generation,
        "seed": generation.get("seed"),
        "results": [
            {
                **row,
                "base_output": outputs["base"][index],
                "adapter_output": outputs["adapter"][index],
            }
            for index, row in enumerate(rows)
        ],
    }
    if output_path is None:
        output_path = (
            resolve_config_path(config["output"]["directory"], config)
            / config["output"]["experiment_name"]
            / "evaluation.json"
        )
    result_path = Path(output_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result["result_path"] = str(result_path)
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture base and fine-tuned outputs on the held-out test split."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = evaluate_base_vs_adapter(args.config, output_path=args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
