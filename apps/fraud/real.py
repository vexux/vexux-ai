"""Real local fraud application composition."""

from __future__ import annotations

from pathlib import Path

import core.composition as core_composition
from core.config import get_config
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend

from apps.fraud.data.neo4j_store import Neo4jFraudStore
from apps.fraud.data.paths import fraud_database_path
from apps.fraud.data.sqlite_store import SQLiteFraudRepository
from apps.fraud.graph_correlation import process_investigation_graph_results
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from apps.fraud.workflow import FraudInvestigationWorkflow


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} must be configured for the real fraud application.")
    return value


def _fraud_database_path(config) -> Path:
    return fraud_database_path(config.sql_database_path)


def close_real_agent(agent) -> None:
    """Close each distinct Neo4j driver owned by a real fraud agent."""
    registry = getattr(agent, "knowledge_graph_registry", None)
    if registry is None:
        return
    closed: set[int] = set()
    for graph_name in ("customer_graph", "fraud_graph"):
        try:
            graph = registry.get(graph_name)
        except KeyError:
            continue
        driver = getattr(graph, "_driver", None)
        if driver is not None and id(driver) not in closed:
            graph.close()
            closed.add(id(driver))


def create_real_agent():
    """Compose the agent with local Neo4j and SQLite fraud resources.

    Real mode deliberately has no fake, in-memory, or implicit seed fallback.
    """
    config = get_config()
    uri = _required(config.neo4j_uri, "NEO4J_URI")
    username = _required(config.neo4j_username, "NEO4J_USERNAME")
    password = _required(config.neo4j_password, "NEO4J_PASSWORD")
    database = config.neo4j_database

    database_path = _fraud_database_path(config)
    repository = SQLiteFraudRepository(database_path)
    repository.require_seeded()
    SQLiteBackend(str(database_path))

    agent = core_composition.create_agent(
        rag_documents_path=Path(__file__).parent / "knowledge"
    )
    driver = None
    try:
        core_graph = agent.knowledge_graph_registry.get(config.neo4j_graph_name)
        driver = core_graph._driver
        graph_store = Neo4jFraudStore(driver, database)
        graph_store.verify_connection()
        graph_store.require_seeded()

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
                driver=driver,
            )
            graph.aliases = aliases
            graph.default_node_id = "C1001"
            graphs.register(graph)

        sources = agent.planner.knowledge_source_registry
        sql = SQLKnowledgeSource(
            SQLiteBackend(str(database_path)),
            default_query=(
                "SELECT transaction_id, account_id, customer_id, merchant_id, "
                "amount, currency, occurred_at, status "
                "FROM transactions WHERE customer_id = %s ORDER BY occurred_at"
            ),
            aliases=("business db", "business database", "sqlite", "sqlite database"),
        )
        sql.name = "business_db"
        sources.register(sql)

        policy = FraudPolicy()
        agent.resource_router.knowledge_graph_registry = graphs
        agent.resource_router.knowledge_source_registry = sources
        agent.execution_manager.knowledge_graph_registry = graphs
        agent.execution_manager.graph_result_processor = process_investigation_graph_results
        agent.execution_manager.knowledge_source_registry = sources
        if agent.execution_manager.knowledge_decision is not None:
            agent.execution_manager.knowledge_decision.knowledge_graph_registry = graphs
            agent.execution_manager.knowledge_decision.knowledge_source_registry = sources
        agent.planner.knowledge_graph_registry = graphs
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
    except Exception:
        if driver is not None:
            driver.close()
        raise


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
    "close_real_agent",
    "create_real_agent",
    "create_real_investigation_service",
    "create_real_investigation_workflow",
]
