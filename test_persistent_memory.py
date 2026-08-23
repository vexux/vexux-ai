from core.memory.registry import MemoryRegistry
from core.memory.sqlite_memory import SQLiteMemory


def test_sqlite_memory_persists_isolates_and_clears(tmp_path):
    path = tmp_path / "memory.db"
    memory = SQLiteMemory(path)
    registry = MemoryRegistry()
    registry.register(memory)
    memory_id = registry.get().store("session-a", "favorite language is Python")

    recreated = SQLiteMemory(path)
    assert recreated.retrieve("session-a", "Python")[0]["memory_id"] == memory_id
    assert recreated.retrieve("session-b") == []
    recreated.clear("session-a")
    assert recreated.retrieve("session-a") == []


def test_sqlite_memory_rejects_obvious_secrets(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.db")
    try:
        memory.store("scope", "Bearer test-secret")
        assert False, "expected sensitive memory rejection"
    except ValueError as exc:
        assert "Sensitive" in str(exc)
