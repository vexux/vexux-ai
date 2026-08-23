import sqlite3
import uuid
from datetime import datetime, timezone

from core.security.redaction import redact_sensitive_data


class SQLiteMemory:
    name = "sqlite"
    description = "Scoped local persistent memory."

    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS memories (memory_id TEXT PRIMARY KEY, scope TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")

    def store(self, scope, content, memory_id=None):
        if not isinstance(scope, str) or not scope or not isinstance(content, str):
            raise ValueError("Memory scope and content must be non-empty strings.")
        # First apply configured redaction patterns
        redacted = redact_sensitive_data(content)
        # Reject obvious secret-like content: redaction marker or purely asterisks
        if "[REDACTED]" in redacted:
            raise ValueError("Sensitive content cannot be persisted.")
        if isinstance(content, str) and content.strip() != "" and all(ch == "*" for ch in content.strip()):
            raise ValueError("Sensitive content cannot be persisted.")
        memory_id = memory_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute("INSERT OR REPLACE INTO memories VALUES (?, ?, ?, COALESCE((SELECT created_at FROM memories WHERE memory_id = ?), ?), ?)", (memory_id, scope, content, memory_id, now, now))
        self.connection.commit()
        return memory_id

    def retrieve(self, scope, query=None, limit=10):
        sql = "SELECT memory_id, content, created_at, updated_at FROM memories WHERE scope = ?"
        values = [scope]
        if query:
            sql += " AND content LIKE ?"
            values.append(f"%{query}%")
        sql += " ORDER BY updated_at DESC LIMIT ?"
        values.append(limit)
        return [dict(zip(("memory_id", "content", "created_at", "updated_at"), row)) for row in self.connection.execute(sql, values)]

    def clear(self, scope):
        self.connection.execute("DELETE FROM memories WHERE scope = ?", (scope,))
        self.connection.commit()
