"""Read-only MySQL backend for SQLKnowledgeSource."""

from __future__ import annotations

from typing import Any, Dict, Iterable


class MySQLBackend:
    """Execute parameterized read-only queries against MySQL."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        database: str,
        port: int = 3306,
        connection_timeout: int = 10,
    ):
        if not host or not user or not database:
            raise ValueError("MySQL configuration requires host, user, and database.")
        if port <= 0:
            raise ValueError("MySQL port must be positive.")
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.connection_timeout = connection_timeout

    def _connect(self):
        try:
            import mysql.connector
        except ImportError as exc:
            raise RuntimeError(
                "MySQL support requires the 'mysql-connector-python' package."
            ) from exc
        try:
            return mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connection_timeout=self.connection_timeout,
            )
        except Exception as exc:
            raise RuntimeError("MySQL connection failed.") from exc

    def execute(
        self,
        query: str,
        parameters: Dict[str, Any] | Iterable[Any] | None = None,
    ):
        connection = self._connect()
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(query, parameters)
            return list(cursor.fetchall())
        except Exception as exc:
            raise RuntimeError("MySQL query failed.") from exc
        finally:
            cursor.close()
            connection.close()

    def schema_metadata(self):
        rows = self.execute(
            "SELECT TABLE_NAME AS table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY TABLE_NAME",
            (self.database,),
        )
        return {"tables": [row["table_name"] for row in rows]}
