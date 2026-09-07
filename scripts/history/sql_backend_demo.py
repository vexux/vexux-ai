"""Demonstrate a real SQLite database through the existing source execution path."""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.policy.default import DefaultPolicy


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "business.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                """
                CREATE TABLE customers (customer_id TEXT PRIMARY KEY, display_name TEXT, status TEXT);
                CREATE TABLE accounts (account_id TEXT PRIMARY KEY, customer_id TEXT, account_type TEXT, status TEXT);
                INSERT INTO customers VALUES ('C1001', 'Alice Smith', 'active');
                INSERT INTO accounts VALUES ('A100', 'C1001', 'checking', 'active');
                INSERT INTO accounts VALUES ('A101', 'C1001', 'savings', 'active');
                """
            )
        finally:
            connection.close()

        source = SQLKnowledgeSource(SQLiteBackend(str(database)))
        source.name = "business_db"
        registry = KnowledgeSourceRegistry()
        registry.register(source)
        task = Task(
            id="sql-demo",
            description="Read customer accounts",
            input={
                "query": "SELECT account_id, account_type, status FROM accounts WHERE customer_id = ?",
                "parameters": ("C1001",),
                "source": "business_db",
            },
            metadata={"capability": "retrieval"},
        )
        result = ExecutionManager(
            knowledge_source_registry=registry,
            policy=DefaultPolicy(),
        ).execute(task, AgentContext(request_id="sql-demo", user_id="investigator"))
        print(f"source = business_db; backend = SQLite; success = {result.success}")
        if result.success:
            print(f"structured result = {result.output['results']}")
            print(f"evidence = {result.output['evidence'].items[0].source}/{result.output['evidence'].items[0].evidence_type}")
        else:
            print(f"error = {result.error}")


if __name__ == "__main__":
    main()
