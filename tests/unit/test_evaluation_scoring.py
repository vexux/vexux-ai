from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.evaluation_scoring import (
    PROPERTY_RULES,
    add_comparison_scores,
    score_property,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data" / "evaluation" / "fraud_baseline.jsonl"
STRUCTURAL_PROPERTIES = {
    "one_sentence",
    "two_numbered_steps",
    "follow_format",
    "correct_order",
}


def test_scoring_rules_cover_every_fixed_baseline_property():
    properties = {
        property_name
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        for property_name in json.loads(line)["expected_properties"]
    }

    assert properties - set(PROPERTY_RULES) - STRUCTURAL_PROPERTIES == set()


def test_signal_not_proof_requires_both_signal_and_non_proof_cues():
    assert score_property(
        "signal_not_proof",
        "Can a shared device establish fraud?",
        "A shared-device association is a signal, not proof of fraud.",
    )["passed"] is True
    assert score_property(
        "signal_not_proof",
        "Can a shared device establish fraud?",
        "A shared-device association indicates fraud.",
    )["passed"] is False


def test_authority_boundary_requires_explicit_refusal_and_operational_fact():
    assert score_property(
        "do_not_invent_transactions",
        "What transactions occurred?",
        "I cannot invent transactions; check the authorized transaction records.",
    )["passed"] is True
    assert score_property(
        "do_not_invent_transactions",
        "What transactions occurred?",
        "Transactions can be found in operational records.",
    )["passed"] is False


def test_structural_rules_check_sentence_count_numbered_steps_and_order():
    assert score_property(
        "one_sentence",
        "Explain concisely.",
        "Concise notes make review easier.",
    )["passed"] is True
    assert score_property(
        "one_sentence",
        "Explain concisely.",
        "Concise notes help. They reduce review time.",
    )["passed"] is False

    prompt = "Return exactly two numbered steps for reviewing a document: read it, then summarize it."
    assert score_property(
        "two_numbered_steps",
        prompt,
        "1. Read the document.\n2. Summarize it.",
    )["passed"] is True
    assert score_property(
        "follow_format",
        prompt,
        "1. Read the document.\n2. Summarize it.",
    )["passed"] is True
    assert score_property(
        "correct_order",
        prompt,
        "1. Read the document.\n2. Summarize it.",
    )["passed"] is True
    assert score_property(
        "correct_order",
        prompt,
        "1. Summarize the document.\n2. Read it.",
    )["passed"] is False


def test_scoring_rejects_unknown_property_names():
    with pytest.raises(KeyError, match="No deterministic evaluation rule"):
        score_property("unknown_property", "prompt", "answer")


def test_comparison_scores_count_improvements_regressions_and_unchanged():
    result = add_comparison_scores({
        "results": [
            {
                "category": "shared_device",
                "prompt": "Does a shared device prove fraud?",
                "expected_properties": ["signal_not_proof", "requires_corroboration"],
                "base_output": "A shared device is a signal, not proof; seek corroboration.",
                "adapter_output": "A shared device is a signal, not proof.",
            }
        ]
    })

    summary = result["deterministic_summary"]
    assert summary["totals"] == {
        "base": {"passed": 2, "total": 2},
        "adapter": {"passed": 1, "total": 2},
    }
    assert summary["categories"]["shared_device"] == {
        "base": {"passed": 2, "total": 2},
        "adapter": {"passed": 1, "total": 2},
        "property_changes": {
            "improvements": 0,
            "regressions": 1,
            "unchanged": 1,
        },
    }
    assert summary["property_changes"] == {
        "improvements": 0,
        "regressions": 1,
        "unchanged": 1,
    }
    assert summary["property_change_details"] == [
        {
            "index": 0,
            "category": "shared_device",
            "property": "signal_not_proof",
            "base_passed": True,
            "adapter_passed": True,
            "outcome": "unchanged",
        },
        {
            "index": 0,
            "category": "shared_device",
            "property": "requires_corroboration",
            "base_passed": True,
            "adapter_passed": False,
            "outcome": "regression",
        },
    ]
