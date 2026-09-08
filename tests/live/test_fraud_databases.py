"""Live local Neo4j/MySQL integration coverage.

These tests are intentionally excluded unless both local services and their
credentials are configured. Normal pytest remains deterministic and offline.
"""

from __future__ import annotations

import pytest

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.config import get_config
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.mysql_backend import MySQLBackend
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource


CONFIG = get_config()

pytestmark = pytest.mark.skipif(
    not all(
        (
            CONFIG.neo4j_uri,
            CONFIG.neo4j_username,
            CONFIG.neo4j_password,
            CONFIG.mysql_password,
        )
    ),
    reason="Local Neo4j/MySQL credentials are not configured.",
)


def _graph(name: str):
    return Neo4jKnowledgeGraph(
        uri=CONFIG.neo4j_uri,
        username=CONFIG.neo4j_username,
        password=CONFIG.neo4j_password,
        database=CONFIG.neo4j_database,
        name=name,
    )


def test_neo4j_seeded_lookup_and_multi_hop_traversal():
    graph = _graph("customer_graph")
    customer = graph.get_node("C1001")
    assert customer["properties"]["name"] == "Alice Smith"
    neighbors = graph.get_neighbors("C1001", direction="outgoing")
    neighbor_ids = {item["node"]["id"] for item in neighbors}
    assert {"A1001", "D5001", "ADDR8001", "F9001"} <= neighbor_ids


def test_mysql_seeded_customer_transactions_alerts_and_schema():
    backend = MySQLBackend(
        host=CONFIG.mysql_host,
        port=CONFIG.mysql_port,
        user=CONFIG.mysql_user,
        password=CONFIG.mysql_password,
        database=CONFIG.mysql_database,
    )
    tables = backend.schema_metadata()["tables"]
    assert {"customers", "accounts", "transactions", "fraud_alerts", "investigations"} <= set(tables)
    transactions = backend.execute(
        "SELECT transaction_id, amount FROM transactions WHERE customer_id = %s",
        ("C1001",),
    )
    assert len(transactions) >= 3
    alerts = backend.execute(
        "SELECT alert_id FROM fraud_alerts WHERE customer_id = %s",
        ("C1001",),
    )
    assert {row["alert_id"] for row in alerts} >= {"ALERT6001", "ALERT6002"}


def test_vexux_registry_adapter_execution_produces_real_source_evidence():
    graphs = KnowledgeGraphRegistry()
    graphs.register(_graph("customer_graph"))
    sources = KnowledgeSourceRegistry()
    source = SQLKnowledgeSource(
        MySQLBackend(
            host=CONFIG.mysql_host,
            port=CONFIG.mysql_port,
            user=CONFIG.mysql_user,
            password=CONFIG.mysql_password,
            database=CONFIG.mysql_database,
        ),
        aliases=("business database",),
    )
    source.name = "business_db"
    sources.register(source)

    manager = ExecutionManager(
        knowledge_graph_registry=graphs,
        knowledge_source_registry=sources,
    )
    graph_result = manager.execute(
        Task(
            id="live-graph",
            description="Read customer graph",
            input={
                "query": "C1001",
                "source": "customer_graph",
                "operation": "get_neighbors",
                "params": {"node_id": "C1001"},
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="live-graph-request", user_id="investigator"),
    )
    assert graph_result.success
    assert graph_result.output["source"] == "customer_graph"
    assert all(item.source == "customer_graph" for item in graph_result.output["evidence"].items)

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
    assert all(item.source == "business_db" for item in sql_result.output["evidence"].items)
