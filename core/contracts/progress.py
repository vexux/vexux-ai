"""Generic progress events for agent runtime consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class ProgressEvent:
    event_type: str
    phase: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: str | None = None
    capability: str | None = None
    resource: str | None = None
    status: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProgressReporter:
    """Send runtime events to an optional application-provided callback."""

    def __init__(self, callback: Callable[[ProgressEvent], None] | None = None):
        self.callback = callback

    def emit(
        self,
        event_type: str,
        phase: str,
        message: str,
        *,
        task_id: str | None = None,
        capability: str | None = None,
        resource: str | None = None,
        status: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressEvent:
        event = ProgressEvent(
            event_type=event_type,
            phase=phase,
            message=message,
            task_id=task_id,
            capability=capability,
            resource=resource,
            status=status,
            duration_ms=duration_ms,
            metadata=dict(metadata or {}),
        )
        if self.callback is not None:
            try:
                self.callback(event)
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Progress callback failed; agent execution continues."
                )
        return event
