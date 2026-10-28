import sqlite3

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from apps.fraud.composition import build_fraud_investigation_graphs
from tests.unit.test_heterogeneous_multigraph import build_registry


def test_three_heterogeneous_sources_share_execution_and_evidence(tmp_path):
    database = tmp_path / "business.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE accounts (account_id TEXT, customer_id TEXT, account_type TEXT, status TEXT);
            INSERT INTO accounts VALUES ('A100', 'C1001', 'checking', 'active');
            INSERT INTO accounts VALUES ('A101', 'C1001', 'savings', 'active');
            INSERT INTO accounts VALUES ('A200', 'C2001', 'checking', 'active');
            """
        )

    graphs = build_registry()
    sources = KnowledgeSourceRegistry()
    sql = SQLKnowledgeSource(SQLiteBackend(str(database)))
    sql.name = "business_db"
    sources.register(sql)
    manager = ExecutionManager(
        knowledge_graph_registry=graphs,
        knowledge_source_registry=sources,
    )
    context = AgentContext(request_id="multi-source")

    graph_task = Task(
        id="graphs",
        description="Read graph relationships",
        input={
            "query": "C1001 relationships",
            "customer_id": "C1001",
            "graph_requests": [
                {"graph_name": "customer_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
                {"graph_name": "fraud_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
            ],
        },
        metadata={"capability": "retrieval"},
    )
    sql_task = Task(
        id="business-db",
        description="Read account details",
        input={
            "query": "SELECT account_id, account_type, status FROM accounts WHERE customer_id = ?",
            "parameters": ("C1001",),
            "source": "business_db",
        },
        metadata={"capability": "retrieval"},
    )
    graph_result = manager.execute(graph_task, context)
    sql_result = manager.execute(sql_task, context)

    assert graph_result.success and sql_result.success
    assert sql_result.output["results"][0]["account_id"] == "A100"
    evidence = graph_result.output["evidence"].items + sql_result.output["evidence"].items
    assert {item.source for item in evidence} == {"customer_graph", "fraud_graph", "business_db"}
    assert any("F900" in item.content for item in evidence)
    assert any(row["account_id"] == "A101" for row in sql_result.output["results"])


def test_multi_source_required_graph_authorization_remains_all_or_nothing():
    from tests.unit.test_authorization import TestPolicy

    registry = build_fraud_investigation_graphs()
    manager = ExecutionManager(
        knowledge_graph_registry=registry,
        policy=TestPolicy(deny_map={"knowledge_graph": {"fraud_graph"}}),
    )
    result = manager.execute(
        Task(
            id="denied",
            description="investigate",
            input={
                "query": "C1001",
                "graph_requests": [
                    {"graph_name": "customer_graph", "operation": "get_node", "params": {"node_id": "C1001"}},
                    {"graph_name": "fraud_graph", "operation": "get_node", "params": {"node_id": "C1001"}},
                ],
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="denied", user_id="restricted_user"),
    )
    assert not result.success
    assert "fraud_graph" in (result.error or "")
