"""Small local observability helpers shared by runtime components."""

from __future__ import annotations

import logging
from threading import Lock
from time import monotonic
from typing import Any

from core.security.redaction import redact_sensitive_data

logger = logging.getLogger("vexux")


class RuntimeMetrics:
    """Thread-safe process-local counters; no external monitoring dependency."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


metrics = RuntimeMetrics()


def classify_error(error: BaseException | str | None) -> str:
    text = str(error or "").lower()
    if (
        "unauthorized" in text
        or "authorization denied" in text
        or "policy denied" in text
        or "access denied" in text
        or "forbidden" in text
    ):
        return "authorization_denial"
    if "invalid" in text or "malformed" in text or "missing" in text:
        return "validation_failure"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "mistral" in text or "ollama" in text or "provider" in text:
        return "provider_unavailable"
    if "retry" in text:
        return "retry_exhausted"
    if "replan" in text:
        return "replanning_exhausted"
    if "source" in text or "graph" in text or "database" in text:
        return "resource_unavailable"
    return "internal_error"


def log_event(event: str, **fields: Any) -> None:
    """Emit bounded, redacted structured fields without prompts or payloads."""
    safe = redact_sensitive_data(fields)
    logger.info(event, extra={"event": event, **safe})


def timed() -> float:
    return monotonic()


def duration_ms(start: float) -> float:
    return round((monotonic() - start) * 1000, 3)


__all__ = ["classify_error", "duration_ms", "log_event", "metrics", "timed"]
