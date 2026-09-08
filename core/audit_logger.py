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


def get_events() -> List[AuditEvent]:
    with _lock:
        return list(_events)


def clear_events() -> None:
    with _lock:
        _events.clear()
