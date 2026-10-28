"""Minimal audit logger (in-memory) for demos and tests.

This file intentionally keeps a tiny surface so it is safe to import from
multiple places without requiring additional composition wiring.
"""
from dataclasses import replace
from threading import Lock
from typing import List

from core.contracts.audit import AuditEvent
from core.security.redaction import redact_sensitive_data

_lock = Lock()
_events: List[AuditEvent] = []


def emit(event: AuditEvent) -> None:
    safe_event = replace(
        event,
        metadata=redact_sensitive_data(event.metadata),
        resource_name=redact_sensitive_data(event.resource_name),
    )
    with _lock:
        _events.append(safe_event)
    try:
        from core.observability_store import get_observability_store
        get_observability_store().persist(
            safe_event.event_type,
            timestamp=safe_event.timestamp,
            request_id=safe_event.request_id,
            session_id=safe_event.session_id,
            actor=safe_event.metadata.get("actor_id"),
            task_id=safe_event.task_id,
            resource=safe_event.resource_name,
            action=safe_event.action,
            status=safe_event.status,
            authorization_decision=(
                "denied" if safe_event.status in {"denied", "error"} else
                "allowed" if safe_event.status == "allowed" else None
            ),
            duration_ms=safe_event.duration_ms,
            metadata=safe_event.metadata,
            sanitized_summary=safe_event.metadata.get("reason"),
        )
    except Exception as exc:
        import logging
        logging.getLogger("vexux.observability").warning(
            "Observability persistence unavailable: %s", type(exc).__name__
        )


def get_events() -> List[AuditEvent]:
    with _lock:
        return list(_events)


def clear_events() -> None:
    with _lock:
        _events.clear()
