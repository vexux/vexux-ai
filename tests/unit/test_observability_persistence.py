import sqlite3

from agent.execution_manager import ExecutionManager
from core.audit_logger import emit, clear_events
from core.contracts.audit import make_event
from core.contracts.execution import AgentContext, Task
from core.observability import log_event
from core.observability_store import SQLiteObservabilityStore
from scripts.manual.run_agent import _handle_observability_command


def test_store_creates_schema_and_persists_across_instances(tmp_path):
    path = tmp_path / "observability.db"
    first = SQLiteObservabilityStore(path)
    first.persist("request_started", request_id="r1", session_id="s1", actor="investigator")

    second = SQLiteObservabilityStore(path)
    rows = second.recent()

    assert rows[0]["request_id"] == "r1"
    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(observability_events)")}
    assert {"timestamp", "request_id", "actor", "event_type", "sanitized_summary"} <= columns


def test_redaction_happens_before_persistence(tmp_path):
    store = SQLiteObservabilityStore(tmp_path / "observability.db")
    store.persist(
        "test",
        request_id="r1",
        error="password=super-secret token=abc123",
        metadata={"api_key": "hidden"},
    )

    row = store.recent()[0]
    assert "super-secret" not in (row["sanitized_summary"] or "")
    assert "abc123" not in (row["sanitized_summary"] or "")
    assert "hidden" not in (row["sanitized_summary"] or "")


def test_audit_and_execution_events_are_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_DB_PATH", str(tmp_path / "observability.db"))
    clear_events()
    emit(make_event(
        "authorization_denied",
        request_id="r2",
        resource_name="fraud_graph",
        action="read",
        status="denied",
        metadata={"actor_id": "support_user", "reason": "denied"},
    ))
    manager = ExecutionManager()
    result = manager.execute(
        Task(id="t1", description="missing", metadata={"capability": "unknown"}),
        AgentContext(request_id="r2", user_id="support_user"),
    )

    rows = SQLiteObservabilityStore(tmp_path / "observability.db").recent()
    assert not result.success
    assert any(row["event_type"] == "authorization_denied" for row in rows)
    assert any(row["event_type"] == "execution.completed" and row["task_id"] == "t1" for row in rows)


def test_store_failure_does_not_break_execution(monkeypatch):
    class BrokenStore:
        def persist(self, *args, **kwargs):
            raise OSError("database unavailable")

    monkeypatch.setattr("core.observability_store.get_observability_store", lambda: BrokenStore())
    result = ExecutionManager().execute(
        Task(id="t1", description="missing", metadata={"capability": "unknown"}),
        AgentContext(request_id="r3"),
    )
    assert not result.success
    assert "Unknown capability" in result.error


def test_metrics_aggregation_and_terminal_commands(tmp_path, capsys):
    store = SQLiteObservabilityStore(tmp_path / "observability.db")
    store.persist("request_started", request_id="r1")
    store.persist("execution.completed", request_id="r1", task_id="t1", capability="tool", success=True, duration_ms=10)
    store.persist("authorization_denied", actor="support_user", resource="fraud_graph", action="read", authorization_decision="denied", success=False)

    assert store.aggregate_metrics() == {
        "total_requests": 1,
        "successes": 1,
        "failures": 0,
        "authorization_denials": 1,
        "average_duration_ms": 10.0,
    }
    assert _handle_observability_command("/metrics", store)
    assert "authorization_denials=1" in capsys.readouterr().out
    assert _handle_observability_command("/trace", store)
    assert "t1" in capsys.readouterr().out
    assert _handle_observability_command("/audit", store)
    assert "fraud_graph" in capsys.readouterr().out
    assert not _handle_observability_command("/unknown", store)
