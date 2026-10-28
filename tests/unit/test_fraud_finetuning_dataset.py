from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.configuration import load_finetuning_config
from training.evaluate import evaluate_base_vs_adapter
from data.validate_fraud_dataset import validate_fraud_dataset


ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "data" / "fraud_finetuning"
EVALUATION_PATH = ROOT / "data" / "evaluation" / "fraud_baseline.jsonl"


def _copy_dataset(destination: Path) -> None:
    destination.mkdir(parents=True)
    for split in ("train", "validation", "test"):
        (destination / f"{split}.jsonl").write_text(
            (DATASET_DIR / f"{split}.jsonl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_fraud_dataset_counts_and_category_distribution():
    report = validate_fraud_dataset(DATASET_DIR, EVALUATION_PATH)

    assert report["valid"] is True, report["errors"]
    assert report["split_counts"] == {"train": 83, "validation": 20, "test": 20}
    assert report["category_counts"]["train"] == {
        "alert_monitoring": 15,
        "authority_boundary": 10,
        "general_retention": 4,
        "policy": 28,
        "response_style": 11,
        "shared_device": 15,
    }
    assert report["evaluation_count"] == 18


def test_splits_have_unique_questions_and_no_exact_leakage():
    questions: dict[str, str] = {}
    full_examples: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        for row in _read_rows(DATASET_DIR / f"{split}.jsonl"):
            question = " ".join(row["messages"][0]["content"].casefold().split())
            serialized = json.dumps(row["messages"], sort_keys=True, separators=(",", ":"))
            assert question not in questions, (
                f"{split} repeats a prompt from {questions.get(question)}"
            )
            assert serialized not in full_examples
            questions[question] = split
            full_examples[serialized] = split


def test_validator_rejects_train_test_prompt_duplication(tmp_path):
    dataset = tmp_path / "dataset"
    _copy_dataset(dataset)
    train_rows = _read_rows(dataset / "train.jsonl")
    test_rows = _read_rows(dataset / "test.jsonl")
    test_rows[0]["messages"][0]["content"] = train_rows[0]["messages"][0]["content"]
    _write_rows(dataset / "test.jsonl", test_rows)

    report = validate_fraud_dataset(dataset, EVALUATION_PATH)

    assert report["valid"] is False
    assert any("duplicates the prompt" in error for error in report["errors"])


def test_validator_rejects_invalid_message_schema(tmp_path):
    dataset = tmp_path / "dataset"
    _copy_dataset(dataset)
    rows = _read_rows(dataset / "validation.jsonl")
    rows[0]["messages"][0]["role"] = "database"
    _write_rows(dataset / "validation.jsonl", rows)

    report = validate_fraud_dataset(dataset, EVALUATION_PATH)

    assert report["valid"] is False
    assert any("expected message roles" in error for error in report["errors"])


def test_validator_rejects_sensitive_live_or_machine_specific_content(tmp_path):
    dataset = tmp_path / "dataset"
    _copy_dataset(dataset)
    rows = _read_rows(dataset / "train.jsonl")
    rows[0]["messages"][1]["content"] += " Use password: sample-secret."
    _write_rows(dataset / "train.jsonl", rows)

    report = validate_fraud_dataset(dataset, EVALUATION_PATH)

    assert report["valid"] is False
    assert any("credential-like assignment" in error for error in report["errors"])


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ("Read C:\\Users\\analyst\\case.txt", "absolute local path"),
        ("MATCH (n)-[r]->(m) RETURN r", "database dump/query content"),
        ("Use ghp_abcdefghijklmnopqrstuvwxyz123456", "secret token"),
    ],
)
def test_validator_rejects_paths_database_queries_and_secret_tokens(
    tmp_path, content, expected_error
):
    dataset = tmp_path / "dataset"
    _copy_dataset(dataset)
    rows = _read_rows(dataset / "train.jsonl")
    rows[0]["messages"][1]["content"] += " " + content
    _write_rows(dataset / "train.jsonl", rows)

    report = validate_fraud_dataset(dataset, EVALUATION_PATH)

    assert report["valid"] is False
    assert any(expected_error in error for error in report["errors"])


def test_validator_rejects_live_demo_identifier(tmp_path):
    dataset = tmp_path / "dataset"
    _copy_dataset(dataset)
    rows = _read_rows(dataset / "train.jsonl")
    rows[0]["messages"][0]["content"] += " Look up C1001."
    _write_rows(dataset / "train.jsonl", rows)

    report = validate_fraud_dataset(dataset, EVALUATION_PATH)

    assert report["valid"] is False
    assert any("live customer/account/transaction identifier" in error for error in report["errors"])


def test_evaluation_uses_the_same_fixed_baseline_prompts_for_both_models(tmp_path):
    prompts_by_mode: dict[str, list[str]] = {}

    class FakeInference:
        def __init__(self, _config_path, *, load_adapter):
            self.mode = "adapter" if load_adapter else "base"
            prompts_by_mode[self.mode] = []

        def generate(self, prompt, **_generation):
            prompts_by_mode[self.mode].append(prompt)
            return f"{self.mode} output"

    result = evaluate_base_vs_adapter(
        output_path=tmp_path / "comparison.json",
        inference_factory=FakeInference,
    )
    expected_categories = {
        "policy",
        "shared_device",
        "alert_handling",
        "transaction_monitoring",
        "authority_boundary",
        "general_retention",
    }

    assert result["test_example_count"] == 18
    assert set(result["evaluation_categories"]) == expected_categories
    assert prompts_by_mode["base"] == prompts_by_mode["adapter"]
    assert all(case["expected_properties"] for case in result["results"])
    assert (tmp_path / "comparison.json").is_file()


def test_dataset_contract_matches_phase_one_configured_path():
    config = load_finetuning_config()

    assert config["dataset"]["directory"] == "data/fraud_finetuning"
    assert (ROOT / config["dataset"]["directory"] / "train.jsonl").is_file()
