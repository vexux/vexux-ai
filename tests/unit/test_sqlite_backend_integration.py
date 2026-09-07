import sqlite3

import pytest

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.policy.default import DefaultPolicy, PolicyDecision


def build_database(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (customer_id TEXT PRIMARY KEY, display_name TEXT, status TEXT);
            CREATE TABLE accounts (account_id TEXT PRIMARY KEY, customer_id TEXT, account_type TEXT, status TEXT);
            INSERT INTO customers VALUES ('C1001', 'Alice Smith', 'active');
            INSERT INTO customers VALUES ('C2001', 'Bob Jones', 'active');
            INSERT INTO accounts VALUES ('A100', 'C1001', 'checking', 'active');
            INSERT INTO accounts VALUES ('A101', 'C1001', 'savings', 'active');
            INSERT INTO accounts VALUES ('A200', 'C2001', 'checking', 'active');
            """
        )


def test_real_sqlite_retrieval_and_structured_evidence(tmp_path):
    database = tmp_path / "business.db"
    build_database(database)
    source = SQLKnowledgeSource(SQLiteBackend(str(database)))
    registry = KnowledgeSourceRegistry()
    source.name = "business_db"
    registry.register(source)
    result = ExecutionManager(
        knowledge_source_registry=registry,
        policy=DefaultPolicy(),
    ).execute(
        Task(
            id="sql-read",
            description="Read accounts",
            input={
                "query": "SELECT account_id, account_type FROM accounts WHERE customer_id = ?",
                "parameters": ("C1001",),
                "source": "business_db",
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="sql-request", user_id="investigator"),
    )
    assert result.success is True
    assert result.output["results"] == [
        {"account_id": "A100", "account_type": "checking"},
        {"account_id": "A101", "account_type": "savings"},
    ]
    assert result.output["evidence"].items[0].source == "business_db"
    assert result.output["evidence"].items[0].evidence_type == "structured_data"


def test_sql_is_read_only_and_single_statement(tmp_path):
    database = tmp_path / "business.db"
    build_database(database)
    source = SQLKnowledgeSource(SQLiteBackend(str(database)))
    for query in (
        "INSERT INTO customers VALUES ('X', 'X', 'active')",
        "UPDATE customers SET status = 'closed'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "SELECT * FROM customers; SELECT * FROM accounts",
    ):
        with pytest.raises(ValueError):
            source.retrieve(query)


def test_missing_database_and_query_failures_are_controlled(tmp_path):
    with pytest.raises(FileNotFoundError):
        SQLiteBackend(str(tmp_path / "missing.db"))
    database = tmp_path / "business.db"
    build_database(database)
    source = SQLKnowledgeSource(SQLiteBackend(str(database)))
    with pytest.raises(RuntimeError, match="SQLite query failed"):
        source.retrieve("SELECT * FROM missing_table")


def test_sql_authorization_denies_before_backend_execution(tmp_path):
    database = tmp_path / "business.db"
    build_database(database)
    source = SQLKnowledgeSource(SQLiteBackend(str(database)))
    source.name = "business_db"
    registry = KnowledgeSourceRegistry()

    class DenyPolicy(DefaultPolicy):
        def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
            return PolicyDecision(False, "restricted", "test")

    registry.register(source)
    result = ExecutionManager(
        knowledge_source_registry=registry,
        policy=DenyPolicy(),
    ).execute(
        Task(
            id="sql-denied",
            description="Read accounts",
            input={"query": "SELECT * FROM customers", "source": "business_db"},
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="sql-denied-request", user_id="restricted_user"),
    )
    assert result.success is False
    assert "Unauthorized access to knowledge source" in result.error
