"""Deterministic quality checks for the curated fraud fine-tuning data."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SPLITS = ("train", "validation", "test")
DATASET_CATEGORIES = {
    "policy",
    "shared_device",
    "alert_monitoring",
    "response_style",
    "authority_boundary",
    "general_retention",
}
EVALUATION_CATEGORIES = {
    "policy",
    "shared_device",
    "alert_handling",
    "transaction_monitoring",
    "authority_boundary",
    "general_retention",
}
SPLIT_COUNT_RANGES = {
    "train": (80, 120),
    "validation": (20, 25),
    "test": (20, 25),
}
LIVE_IDENTIFIER = re.compile(
    r"\b(?:C\d{4}|A\d{4}|T\d{5}|M\d{4}|D\d{4}|F\d{4}|"
    r"ADDR\d{4}|ALERT\d{4}|INV\d{4})\b",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT = re.compile(
    r"\b(?:password|passwd|api[_ -]?key|secret|access[_ -]?token|"
    r"client[_ -]?secret)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)
SECRET_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,})\b"
)
ABSOLUTE_PATH = re.compile(
    r"(?:\b[A-Za-z]:\\|\\\\[A-Za-z0-9_.-]+\\|"
    r"(?<!\w)/(?:home|Users|tmp|var|etc)/)",
    re.IGNORECASE,
)
DATABASE_DUMP = re.compile(
    r"\b(?:INSERT\s+INTO|CREATE\s+TABLE|UNWIND\s+\[|MATCH\s*\([^)]*\)-\[)",
    re.IGNORECASE,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        errors.append(f"Missing JSONL file: {path}")
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                errors.append(f"{path}:{line_number}: blank lines are not allowed.")
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON: {exc.msg}.")
                continue
            if not isinstance(record, dict):
                errors.append(f"{path}:{line_number}: each row must be a JSON object.")
                continue
            records.append(record)
    return records


def _validate_training_record(
    record: dict[str, Any],
    *,
    split: str,
    index: int,
    errors: list[str],
) -> tuple[str, str]:
    location = f"{split} example {index + 1}"
    category = record.get("category")
    if category not in DATASET_CATEGORIES:
        errors.append(f"{location}: unsupported or missing category {category!r}.")

    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        errors.append(f"{location}: messages must contain exactly user and assistant turns.")
        return str(category), ""
    roles = [message.get("role") if isinstance(message, dict) else None for message in messages]
    if roles != ["user", "assistant"]:
        errors.append(f"{location}: expected message roles ['user', 'assistant'], got {roles!r}.")

    contents: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            errors.append(f"{location}: message content must be a non-empty string.")
            continue
        if len(content) > 1800:
            errors.append(f"{location}: message content exceeds the 1800-character limit.")
        contents.append(content)

    if len(contents) != 2:
        return str(category), ""
    serialized = _canonical(messages)
    joined = "\n".join(contents)
    for label, pattern in (
        ("live customer/account/transaction identifier", LIVE_IDENTIFIER),
        ("credential-like assignment", SECRET_ASSIGNMENT),
        ("secret token", SECRET_TOKEN),
        ("absolute local path", ABSOLUTE_PATH),
        ("database dump/query content", DATABASE_DUMP),
    ):
        if pattern.search(joined):
            errors.append(f"{location}: contains {label}.")
    return str(category), serialized


def validate_fraud_dataset(
    dataset_dir: str | Path = "data/fraud_finetuning",
    evaluation_path: str | Path = "data/evaluation/fraud_baseline.jsonl",
) -> dict[str, Any]:
    errors: list[str] = []
    root = Path(dataset_dir)
    split_records = {
        split: _read_jsonl(root / f"{split}.jsonl", errors)
        for split in SPLITS
    }
    counts = {split: len(records) for split, records in split_records.items()}
    category_counts: dict[str, dict[str, int]] = {}
    all_prompts: dict[str, tuple[str, int]] = {}
    all_examples: dict[str, str] = {}
    for split in SPLITS:
        minimum, maximum = SPLIT_COUNT_RANGES[split]
        if not minimum <= counts[split] <= maximum:
            errors.append(
                f"{split} split must contain {minimum}-{maximum} examples; found {counts[split]}."
            )
        split_categories: Counter[str] = Counter()
        for index, record in enumerate(split_records[split]):
            category, canonical = _validate_training_record(
                record,
                split=split,
                index=index,
                errors=errors,
            )
            split_categories[category] += 1
            messages = record.get("messages")
            if isinstance(messages, list) and messages and isinstance(messages[0], dict):
                prompt = messages[0].get("content")
                if isinstance(prompt, str):
                    normalized_prompt = " ".join(prompt.casefold().split())
                    if normalized_prompt in all_prompts:
                        other_split, other_index = all_prompts[normalized_prompt]
                        errors.append(
                            f"{split} example {index + 1} duplicates the prompt in "
                            f"{other_split} example {other_index}."
                        )
                    else:
                        all_prompts[normalized_prompt] = (split, index + 1)
            if canonical:
                if canonical in all_examples:
                    errors.append(
                        f"{split} example {index + 1} exactly duplicates "
                        f"{all_examples[canonical]}."
                    )
                else:
                    all_examples[canonical] = f"{split} example {index + 1}"
        missing_categories = DATASET_CATEGORIES - set(split_categories)
        if missing_categories and counts[split]:
            errors.append(
                f"{split} split is missing category coverage for: "
                + ", ".join(sorted(missing_categories))
            )
        category_counts[split] = dict(sorted(split_categories.items()))

    eval_path = Path(evaluation_path)
    evaluation_records = _read_jsonl(eval_path, errors)
    evaluation_counts: Counter[str] = Counter()
    evaluation_prompts: set[str] = set()
    for index, case in enumerate(evaluation_records):
        location = f"evaluation case {index + 1}"
        category = case.get("category")
        prompt = case.get("prompt")
        expected = case.get("expected_properties")
        if category not in EVALUATION_CATEGORIES:
            errors.append(f"{location}: unsupported or missing category {category!r}.")
        else:
            evaluation_counts[category] += 1
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{location}: prompt must be a non-empty string.")
            continue
        if len(prompt) > 1800:
            errors.append(f"{location}: prompt exceeds the 1800-character limit.")
        normalized_prompt = " ".join(prompt.casefold().split())
        if normalized_prompt in evaluation_prompts:
            errors.append(f"{location}: duplicate evaluation prompt.")
        evaluation_prompts.add(normalized_prompt)
        if (
            not isinstance(expected, list)
            or not expected
            or any(not isinstance(item, str) or not item.strip() for item in expected)
        ):
            errors.append(f"{location}: expected_properties must be a non-empty string list.")
        case_content = _canonical(case)
        for label, pattern in (
            ("live customer/account/transaction identifier", LIVE_IDENTIFIER),
            ("credential-like assignment", SECRET_ASSIGNMENT),
            ("secret token", SECRET_TOKEN),
            ("absolute local path", ABSOLUTE_PATH),
            ("database dump/query content", DATABASE_DUMP),
        ):
            if pattern.search(case_content):
                errors.append(f"{location}: contains {label}.")

    leaked_evaluation_prompts = evaluation_prompts.intersection(all_prompts)
    if leaked_evaluation_prompts:
        errors.append(
            f"{len(leaked_evaluation_prompts)} baseline evaluation prompt(s) "
            "also occur in a training, validation, or test split."
        )

    missing_eval_categories = EVALUATION_CATEGORIES - set(evaluation_counts)
    if missing_eval_categories:
        errors.append(
            "Evaluation set is missing category coverage for: "
            + ", ".join(sorted(missing_eval_categories))
        )

    return {
        "valid": not errors,
        "errors": errors,
        "split_counts": counts,
        "category_counts": category_counts,
        "evaluation_count": len(evaluation_records),
        "evaluation_category_counts": dict(sorted(evaluation_counts.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the curated fraud QLoRA datasets.")
    parser.add_argument("--dataset-dir", default="data/fraud_finetuning")
    parser.add_argument("--evaluation", default="data/evaluation/fraud_baseline.jsonl")
    args = parser.parse_args(argv)
    report = validate_fraud_dataset(args.dataset_dir, args.evaluation)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
