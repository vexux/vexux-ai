"""Synthetic reference composition for the interactive fraud demonstration."""

from contextlib import contextmanager
import os
import sqlite3
import tempfile
from pathlib import Path

import core.composition as composition
from apps.fraud.composition import build_fraud_investigation_graphs
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.policy.default import DefaultPolicy, PolicyDecision


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
            )
        finally:
            connection.close()

        graphs = build_fraud_investigation_graphs()
        sources = KnowledgeSourceRegistry()
        sql = SQLKnowledgeSource(
            SQLiteBackend(str(database)),
            default_query="SELECT * FROM accounts",
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
        yield agent
