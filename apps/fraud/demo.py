"""Application-specific runtime composition for the fraud demo workload."""

from __future__ import annotations

from contextlib import contextmanager
import os
import sqlite3
import tempfile
from pathlib import Path

import core.composition as composition
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from apps.fraud.composition import build_fraud_investigation_graphs
from apps.fraud.graph_correlation import process_investigation_graph_results
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from apps.fraud.workflow import FraudInvestigationWorkflow


DemoPolicy = FraudPolicy
FRAUD_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


@contextmanager
def create_demo_agent():
    """Compose the generic agent with removable synthetic demo resources."""
    provider_was_set = "MODEL_PROVIDER" in os.environ
    previous_provider = os.environ.get("MODEL_PROVIDER")
    if not provider_was_set:
        os.environ["MODEL_PROVIDER"] = "fake"
    try:
        agent = composition.create_agent(rag_documents_path=FRAUD_KNOWLEDGE_DIR)
    finally:
        if provider_was_set:
            os.environ["MODEL_PROVIDER"] = previous_provider
        else:
            os.environ.pop("MODEL_PROVIDER", None)

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "business.db"
        connection = sqlite3.connect(database)
        try:
            fixture_path = Path(__file__).parent / "data" / "sqlite" / "demo.sql"
            connection.executescript(fixture_path.read_text(encoding="utf-8"))
        finally:
            connection.close()

        graphs = build_fraud_investigation_graphs()
        sources = KnowledgeSourceRegistry()
        sql = SQLKnowledgeSource(
            SQLiteBackend(str(database)),
            default_query="SELECT * FROM accounts WHERE customer_id = ?",
            aliases=("business db", "sqlite", "sqlite db", "sqlite database"),
        )
        sql.name = "business_db"
        sources.register(sql)

        agent.resource_router.knowledge_graph_registry = graphs
        agent.resource_router.knowledge_source_registry = sources
        agent.execution_manager.knowledge_graph_registry = graphs
        agent.execution_manager.graph_result_processor = process_investigation_graph_results
        agent.execution_manager.knowledge_source_registry = sources
        knowledge_decision = getattr(agent.execution_manager, "knowledge_decision", None)
        if knowledge_decision is not None:
            knowledge_decision.knowledge_graph_registry = graphs
            knowledge_decision.knowledge_source_registry = sources
        agent.knowledge_graph_registry = graphs
        demo_policy = FraudPolicy()
        agent.policy = demo_policy
        agent.execution_manager.policy = demo_policy
        workflow_registry = getattr(agent, "workflow_registry", None)
        if workflow_registry is not None:
            workflow_registry.register(FraudInvestigationWorkflow(
                investigation_service=FraudInvestigationService(
                    graph_registry=graphs,
                    source_registry=sources,
                    policy=demo_policy,
                ),
                execution_manager=agent.execution_manager,
                resource_router=agent.resource_router,
            ))
        yield agent
