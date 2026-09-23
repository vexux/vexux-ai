"""Best-effort local SQLite persistence for sanitized observability events."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from core.security.redaction import redact_sensitive_data

LOGGER = logging.getLogger("vexux.observability")
DEFAULT_OBSERVABILITY_DB_PATH = "data/observability/vexux_observability.db"


class SQLiteObservabilityStore:
    """Small queryable store; storage failures are isolated from application work."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        configured = path or os.getenv("OBSERVABILITY_DB_PATH") or DEFAULT_OBSERVABILITY_DB_PATH
        self.path = Path(configured)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self._lock = Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=2)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS observability_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    request_id TEXT,
                    session_id TEXT,
                    actor TEXT,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    capability TEXT,
                    resource TEXT,
                    action TEXT,
                    authorization_decision TEXT,
                    success INTEGER,
                    duration_ms REAL,
                    error_category TEXT,
                    sanitized_summary TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observability_timestamp "
                "ON observability_events(timestamp)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observability_request "
                "ON observability_events(request_id)"
            )

    @staticmethod
    def _summary(value: Any) -> str | None:
        if value is None:
            return None
        safe = redact_sensitive_data(value)
        if isinstance(safe, (dict, list, tuple)):
            safe = json.dumps(safe, default=str, sort_keys=True)
        return str(safe)[:1000]

    def persist(self, event_type: str, **fields: Any) -> bool:
        """Persist only normalized, redacted fields and never raise to callers."""
        try:
            safe = redact_sensitive_data(fields)
            metadata = safe.get("metadata") if isinstance(safe, dict) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            status = safe.get("status")
            authorization = (
                safe.get("authorization_decision")
                or metadata.get("authorization_decision")
                or ("denied" if safe.get("authorization_denied") else None)
            )
            success = safe.get("success")
            if success is None and status is not None:
                success = str(status).lower() in {"success", "successful", "completed", "allowed", "succeeded"}
                if str(status).lower() in {"failed", "failure", "denied", "error"}:
                    success = False
            resource = safe.get("resource") or safe.get("resource_name") or metadata.get("resource")
            capability = safe.get("capability") or metadata.get("capability")
            summary_value = safe.get("sanitized_summary") or safe.get("error") or safe.get("summary")
            row = (
                safe.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                safe.get("request_id"),
                safe.get("session_id"),
                safe.get("actor") or safe.get("actor_id") or metadata.get("actor_id"),
                event_type,
                safe.get("task_id"),
                capability,
                resource,
                safe.get("action"),
                authorization,
                None if success is None else int(bool(success)),
                safe.get("duration_ms"),
                safe.get("error_category"),
                self._summary(summary_value),
            )
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO observability_events
                    (timestamp, request_id, session_id, actor, event_type, task_id,
                     capability, resource, action, authorization_decision, success,
                     duration_ms, error_category, sanitized_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            return True
        except Exception as exc:  # observability must never interrupt application work
            LOGGER.warning("Observability persistence unavailable: %s", type(exc).__name__)
            return False

    def recent(self, limit: int = 20, *, event_type: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            values.append(event_type)
        if request_id:
            clauses.append("request_id = ?")
            values.append(request_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM observability_events{where} ORDER BY id DESC LIMIT ?",
                (*values, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregate_metrics(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT CASE WHEN event_type IN ('request_started', 'agent.request.started')
                                         THEN request_id END) AS total_requests,
                    SUM(CASE WHEN event_type IN ('execution.completed', 'request_completed')
                              AND success = 1 THEN 1 ELSE 0 END) AS successes,
                    SUM(CASE WHEN event_type IN ('execution.completed', 'request_completed')
                              AND success = 0 THEN 1 ELSE 0 END) AS failures,
                    SUM(CASE WHEN authorization_decision = 'denied' THEN 1 ELSE 0 END) AS authorization_denials,
                    AVG(CASE WHEN event_type = 'execution.completed' THEN duration_ms END) AS average_duration_ms
                FROM observability_events
                """
            ).fetchone()
        return {
            "total_requests": int(row["total_requests"] or 0),
            "successes": int(row["successes"] or 0),
            "failures": int(row["failures"] or 0),
            "authorization_denials": int(row["authorization_denials"] or 0),
            "average_duration_ms": round(float(row["average_duration_ms"] or 0), 3),
        }


def get_observability_store(path: str | None = None) -> SQLiteObservabilityStore:
    if path is None:
        try:
            from core.config import get_config
            path = get_config().observability_db_path
        except Exception:
            path = None
    return SQLiteObservabilityStore(path)


__all__ = [
    "DEFAULT_OBSERVABILITY_DB_PATH",
    "SQLiteObservabilityStore",
    "get_observability_store",
]
