"""Held-out base-versus-adapter output capture for fine-tuning experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from training.configuration import (
    DEFAULT_CONFIG_PATH,
    load_finetuning_config,
    resolve_config_path,
)
from training.inference import InferencePipeline


def evaluate_base_vs_adapter(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    output_path: str | Path | None = None,
    inference_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    config = load_finetuning_config(config_path)
    dataset_path = resolve_config_path(config["evaluation"]["baseline_path"], config)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Baseline evaluation set was not found: {dataset_path}")
    cases = []
    with dataset_path.open("r", encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid baseline evaluation JSON at {dataset_path}:{line_number}."
                ) from exc
            prompt = case.get("prompt")
            category = case.get("category")
            expected_properties = case.get("expected_properties")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(
                    f"Baseline evaluation case {line_number} needs a non-empty prompt."
                )
            if not isinstance(category, str) or not category.strip():
                raise ValueError(
                    f"Baseline evaluation case {line_number} needs a category."
                )
            if (
                not isinstance(expected_properties, list)
                or not expected_properties
                or any(not isinstance(item, str) or not item for item in expected_properties)
            ):
                raise ValueError(
                    f"Baseline evaluation case {line_number} needs expected_properties."
                )
            cases.append({
                "index": len(cases),
                "category": category,
                "prompt": prompt,
                "expected_properties": expected_properties,
            })
    if not cases:
        raise ValueError("The baseline evaluation set must not be empty.")

    inference_type = inference_factory or InferencePipeline
    generation = dict(config["generation"])

    outputs: dict[str, list[str]] = {"base": [], "adapter": []}
    for mode in ("base", "adapter"):
        pipeline = inference_type(config_path, load_adapter=(mode == "adapter"))
        try:
            outputs[mode] = [
                pipeline.generate(case["prompt"], **generation)
                for case in cases
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
        "evaluation_categories": sorted({case["category"] for case in cases}),
        "test_example_count": len(cases),
        "generation_config": generation,
        "seed": generation.get("seed"),
        "results": [
            {
                **case,
                "base_output": outputs["base"][index],
                "adapter_output": outputs["adapter"][index],
            }
            for index, case in enumerate(cases)
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
