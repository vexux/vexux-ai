"""Generic interpretation of explicit conversational follow-up requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_FOLLOW_UP_PATTERNS = (
    (
        "expand",
        re.compile(r"^\s*in\s+(?:more\s+)?detail(?:s)?[.!? ]*$", re.IGNORECASE),
    ),
    ("explain", re.compile(r"^\s*explain\s+(?:that|this|it)\b", re.IGNORECASE)),
    (
        "expand",
        re.compile(r"^\s*(?:give|provide)\s+me\s+more\s+information\b", re.IGNORECASE),
    ),
    (
        "summarize",
        re.compile(r"^\s*summarize\s+(?:that|this|it|the\s+above)\b", re.IGNORECASE),
    ),
    (
        "summarize",
        re.compile(r"^\s*summarize\s+the\s+[\w-]+(?:\s+[\w-]+){0,3}\b", re.IGNORECASE),
    ),
    (
        "expand",
        re.compile(r"^\s*expand\s+(?:on\s+)?(?:the\s+)?previous\s+result\b", re.IGNORECASE),
    ),
    (
        "reference",
        re.compile(
            r"^\s*what\s+about\s+(?:the\s+)?(?:second|last|first|next|previous|that|those|it)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reference",
        re.compile(r"^\s*what\s+about\s+the\s+[\w-]+(?:\s+[\w-]+){0,3}\b", re.IGNORECASE),
    ),
    (
        "reference",
        re.compile(r"^\s*show\s+(?:me\s+)?the\s+[\w-]+(?:\s+[\w-]+){0,2}\b", re.IGNORECASE),
    ),
    (
        "reference",
        re.compile(
            r"^\s*compare\s+(?:that|this|it|the\s+(?:previous|prior|last)\s+[\w-]+)"
            r"\s+with\b",
            re.IGNORECASE,
        ),
    ),
    ("reference", re.compile(r"^\s*what\s+about\s+it\b", re.IGNORECASE)),
    ("reference", re.compile(r"^\s*what\s+about\s+the\s+second\s+one\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class FollowUpRequest:
    query: str
    planning_query: str
    previous_turn: dict[str, Any]
    kind: str = "reference"
    base_query: str = ""


def interpret_follow_up(
    query: str,
    conversation_context: list[dict[str, Any]] | None,
) -> FollowUpRequest | None:
    """Contextualize only explicit reference-style requests with prior history."""
    history = conversation_context or []
    match = next(
        ((kind, pattern) for kind, pattern in _FOLLOW_UP_PATTERNS if pattern.search(query)),
        None,
    )
    if not history or match is None:
        return None
    previous_turn = history[-1]
    original_query = str(previous_turn.get("query", "")).strip()
    if not original_query:
        return None
    preceding_follow_up = interpret_follow_up(original_query, history[:-1])
    if preceding_follow_up is not None:
        original_query = preceding_follow_up.base_query
    return FollowUpRequest(
        query=query,
        planning_query=f"{original_query}\nFollow-up request: {query}",
        previous_turn=previous_turn,
        kind=match[0],
        base_query=original_query,
    )
