"""Real local fraud application composition."""

from __future__ import annotations

import core.composition as core_composition
from core.config import get_config
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.mysql_backend import MySQLBackend
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource

from apps.fraud.policy import FraudPolicy
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.workflow import FraudInvestigationWorkflow


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} must be configured for the real fraud application.")
    return value


def create_real_agent():
    """Compose the agent with real local Neo4j and MySQL resources.

    This function intentionally has no fake or in-memory fallback. Tests and the
    synthetic demo use their separate application compositions.
    """
    config = get_config()
    uri = _required(config.neo4j_uri, "NEO4J_URI")
    username = _required(config.neo4j_username, "NEO4J_USERNAME")
    password = _required(config.neo4j_password, "NEO4J_PASSWORD")
    database = config.neo4j_database
    mysql_password = _required(config.mysql_password, "MYSQL_PASSWORD")

    agent = core_composition.create_agent()

    graphs = KnowledgeGraphRegistry()
    for name, aliases in (
        ("customer_graph", ("customer", "customer graph")),
        ("fraud_graph", ("fraud", "fraud graph")),
    ):
        graph = Neo4jKnowledgeGraph(
            uri=uri,
            username=username,
            password=password,
            database=database,
            name=name,
        )
        graph.aliases = aliases
        graph.default_node_id = "C1001"
        graphs.register(graph)

    sources = KnowledgeSourceRegistry()
    sql = SQLKnowledgeSource(
        MySQLBackend(
            host=config.mysql_host,
            port=config.mysql_port,
            user=config.mysql_user,
            password=mysql_password,
            database=config.mysql_database,
        ),
        default_query=(
            "SELECT transaction_id, account_id, customer_id, merchant_id, "
            "amount, currency, occurred_at, status "
            "FROM transactions WHERE customer_id = %s ORDER BY occurred_at"
        ),
        aliases=("business db", "business database", "mysql", "mysql database"),
    )
    sql.name = "business_db"
    sources.register(sql)

    policy = FraudPolicy()
    agent.resource_router.knowledge_graph_registry = graphs
    agent.resource_router.knowledge_source_registry = sources
    agent.execution_manager.knowledge_graph_registry = graphs
    agent.execution_manager.knowledge_source_registry = sources
    if agent.execution_manager.knowledge_decision is not None:
        agent.execution_manager.knowledge_decision.knowledge_graph_registry = graphs
        agent.execution_manager.knowledge_decision.knowledge_source_registry = sources
    agent.knowledge_graph_registry = graphs
    agent.policy = policy
    agent.execution_manager.policy = policy
    fraud_workflow = FraudInvestigationWorkflow(
        investigation_service=FraudInvestigationService(
            graph_registry=graphs,
            source_registry=sources,
            policy=policy,
        ),
        execution_manager=agent.execution_manager,
        resource_router=agent.resource_router,
    )
    agent.workflow_registry.register(fraud_workflow)
    return agent


def create_real_investigation_service() -> FraudInvestigationService:
    """Compose the deterministic investigation service with real resources."""
    agent = create_real_agent()
    return FraudInvestigationService(
        graph_registry=agent.knowledge_graph_registry,
        source_registry=agent.execution_manager.knowledge_source_registry,
        policy=agent.policy,
    )


def create_real_investigation_workflow():
    """Compose the bounded workflow with the real registered resources."""
    agent = create_real_agent()
    return agent.workflow_registry.get("fraud_investigation")


__all__ = [
    "create_real_agent",
    "create_real_investigation_service",
    "create_real_investigation_workflow",
]
