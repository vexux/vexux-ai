"""Opt-in live local Neo4j and SQLite integration coverage."""

from __future__ import annotations

import sqlite3

import pytest

from agent.execution_manager import ExecutionManager
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from apps.fraud.data.paths import fraud_database_path
from core.config import get_config
from core.contracts.execution import AgentContext, Task
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend


CONFIG = get_config()
DATABASE_PATH = fraud_database_path(CONFIG.sql_database_path)

pytestmark = pytest.mark.skipif(
    not (
        CONFIG.neo4j_uri
        and CONFIG.neo4j_username
        and CONFIG.neo4j_password
        and DATABASE_PATH.is_file()
    ),
    reason="Local seeded Neo4j and SQLite fraud data are not configured.",
)


@pytest.fixture
def fraud_resources():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        CONFIG.neo4j_uri,
        auth=(CONFIG.neo4j_username, CONFIG.neo4j_password),
    )
    graphs = KnowledgeGraphRegistry()
    for name in ("customer_graph", "fraud_graph"):
        graph = Neo4jKnowledgeGraph(
            uri=CONFIG.neo4j_uri,
            username=CONFIG.neo4j_username,
            password=CONFIG.neo4j_password,
            database=CONFIG.neo4j_database,
            name=name,
            driver=driver,
        )
        graphs.register(graph)
    sources = KnowledgeSourceRegistry()
    source = SQLKnowledgeSource(SQLiteBackend(str(DATABASE_PATH)))
    source.name = "business_db"
    sources.register(source)
    try:
        yield graphs, sources
    finally:
        driver.close()


def test_neo4j_canonical_customer_and_shared_device_traversal(fraud_resources):
    graphs, _ = fraud_resources
    graph = graphs.get("customer_graph")
    customer = graph.get_node("C1001")
    assert customer["properties"]["name"] == "Alice Smith"
    assert graph.get_node("C1005")["properties"]["name"] == "Evan Brooks"
    neighbors = graph.get_neighbors("C1001", direction="outgoing")
    assert {"A1001", "D5001", "ADDR8001", "F9001"} <= {
        item["node"]["id"] for item in neighbors
    }
    c1002_neighbors = graph.get_neighbors("C1002", direction="outgoing")
    assert "D5001" in {item["node"]["id"] for item in c1002_neighbors}


def test_sqlite_canonical_records_and_foreign_keys():
    assert SQLiteBackend(str(DATABASE_PATH)).execute("PRAGMA foreign_keys") == [
        {"foreign_keys": 1}
    ]
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE customer_id = 'C1001'"
        ).fetchone()[0] == 5
        assert connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE customer_id = 'C1002'"
        ).fetchone()[0] == 4
        assert connection.execute(
            """
            SELECT COUNT(*) FROM fraud_alerts
            WHERE customer_id = 'C1001' AND severity = 'high' AND status = 'open'
            """
        ).fetchone()[0] == 2
        assert connection.execute(
            """
            SELECT COUNT(*) FROM fraud_alerts
            WHERE customer_id = 'C1002' AND severity = 'low' AND status = 'closed'
            """
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_live_investigation_keeps_c1002_medium_and_c1001_high(fraud_resources):
    graphs, sources = fraud_resources
    service = FraudInvestigationService(graphs, sources, FraudPolicy())

    c1001 = service.investigate("C1001", actor="investigator")
    c1002 = service.investigate("C1002", actor="investigator")

    assert c1001.risk_assessment == "high"
    assert c1001.metadata["transaction_count"] == 5
    assert c1001.metadata["alert_count"] == 2
    assert c1002.risk_assessment == "medium"
    assert "shared_device_relationship" in c1002.contributing_signals
    assert c1002.metadata["transaction_count"] == 4
    assert c1002.metadata["alert_count"] == 1


def test_live_investigation_rejects_missing_customer_and_unauthorized_actor(
    fraud_resources,
):
    graphs, sources = fraud_resources
    service = FraudInvestigationService(graphs, sources, FraudPolicy())

    with pytest.raises(KeyError, match="Node not found"):
        service.investigate("C9999", actor="investigator")
    with pytest.raises(PermissionError, match="Unauthorized access"):
        service.investigate("C1001", actor="support_user")


def test_vexux_registry_adapter_execution_produces_sqlite_evidence(fraud_resources):
    graphs, sources = fraud_resources
    manager = ExecutionManager(
        knowledge_graph_registry=graphs,
        knowledge_source_registry=sources,
    )
    sql_result = manager.execute(
        Task(
            id="live-sql",
            description="Read business database",
            input={
                "query": (
                    "SELECT transaction_id, customer_id FROM transactions "
                    "WHERE customer_id = %s"
                ),
                "source": "business_db",
                "parameters": ("C1001",),
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="live-sql-request", user_id="investigator"),
    )
    assert sql_result.success
    assert sql_result.output["source"] == "business_db"
    assert len(sql_result.output["results"]) == 5
    assert all(item.source == "business_db" for item in sql_result.output["evidence"].items)
