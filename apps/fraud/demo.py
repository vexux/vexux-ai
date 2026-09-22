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
from core.policy.default import DefaultPolicy, PolicyDecision

from apps.fraud.composition import build_fraud_investigation_graphs
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.workflow import FraudInvestigationWorkflow


class DemoPolicy(DefaultPolicy):
    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if actor == "support_user" and resource_name == "fraud_graph":
            return PolicyDecision(False, "support_user cannot access fraud_graph", "demo_policy")
        return super().authorize_resource(actor, resource_type, resource_name, action, context)


class _DemoRAGPipeline:
    """Avoid loading the optional local embedding model for resource demos."""

    def __init__(self, *args, **kwargs):
        pass

    def retrieve(self, query, k=None):
        if "ec2" in query.lower():
            return [{
                "score": 1.0,
                "document": "Amazon EC2 provides resizable compute capacity in the cloud.",
            }]
        return []


@contextmanager
def create_demo_agent():
    """Compose the generic agent with removable synthetic demo resources."""
    provider_was_set = "MODEL_PROVIDER" in os.environ
    previous_provider = os.environ.get("MODEL_PROVIDER")
    if not provider_was_set:
        os.environ["MODEL_PROVIDER"] = "fake"
    try:
        original_rag_pipeline = composition.RAGPipeline
        composition.RAGPipeline = _DemoRAGPipeline
        try:
            agent = composition.create_agent()
        finally:
            composition.RAGPipeline = original_rag_pipeline
    finally:
        if provider_was_set:
            os.environ["MODEL_PROVIDER"] = previous_provider
        else:
            os.environ.pop("MODEL_PROVIDER", None)

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "business.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                "CREATE TABLE accounts (account_id TEXT, customer_id TEXT, status TEXT);"
                "INSERT INTO accounts VALUES ('A100', 'C1001', 'active');"
                "CREATE TABLE transactions (transaction_id TEXT, account_id TEXT, customer_id TEXT, merchant_id TEXT, amount REAL, status TEXT, occurred_at TEXT);"
                "INSERT INTO transactions VALUES ('T1001', 'A100', 'C1001', 'M100', 120.0, 'posted', '2026-01-01');"
                "CREATE TABLE fraud_alerts (alert_id TEXT, customer_id TEXT, transaction_id TEXT, alert_type TEXT, severity TEXT, status TEXT, created_at TEXT);"
                "INSERT INTO fraud_alerts VALUES ('AL1001', 'C1001', 'T1001', 'velocity', 'high', 'open', '2026-01-01');"
                "CREATE TABLE investigations (investigation_id TEXT, customer_id TEXT, fraud_case_id TEXT, status TEXT, opened_at TEXT);"
                "INSERT INTO investigations VALUES ('I1001', 'C1001', 'F900', 'open', '2026-01-01');"
            )
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
        agent.execution_manager.knowledge_source_registry = sources
        knowledge_decision = getattr(agent.execution_manager, "knowledge_decision", None)
        if knowledge_decision is not None:
            knowledge_decision.knowledge_graph_registry = graphs
            knowledge_decision.knowledge_source_registry = sources
        agent.knowledge_graph_registry = graphs
        demo_policy = DemoPolicy()
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
