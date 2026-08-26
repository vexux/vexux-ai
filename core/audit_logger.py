"""Minimal audit logger (in-memory) for demos and tests.

This file intentionally keeps a tiny surface so it is safe to import from
multiple places without requiring additional composition wiring.
"""
from threading import Lock
from typing import List

from core.contracts.audit import AuditEvent, make_event

_lock = Lock()
_events: List[AuditEvent] = []


def emit(event: AuditEvent) -> None:
    with _lock:
        _events.append(event)


def get_events() -> List[AuditEvent]:
    with _lock:
        return list(_events)


def clear_events() -> None:
    with _lock:
        _events.clear()
