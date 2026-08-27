"""Read-only SQLite backend for SQLKnowledgeSource."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable


class SQLiteBackend:
    """Execute parameterized read-only queries against an existing SQLite file."""

    def __init__(self, database_path: str):
        if not database_path:
            raise ValueError("SQL database path must not be empty.")
        self.database_path = str(Path(database_path).expanduser())
        if not Path(self.database_path).is_file():
            raise FileNotFoundError(f"SQLite database not found: {self.database_path}")

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{Path(self.database_path).resolve().as_posix()}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def execute(self, query: str, parameters: Dict[str, Any] | Iterable[Any] | None = None):
        connection = self._connect()
        try:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(query, parameters or {})
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise RuntimeError("SQLite query failed.") from exc
        finally:
            connection.close()

    def schema_metadata(self):
        rows = self.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return {"tables": [row["name"] for row in rows]}
