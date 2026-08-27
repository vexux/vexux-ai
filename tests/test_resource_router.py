import pytest

from core.knowledge.multi_graph import build_fraud_investigation_graphs
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.resource_router import ResourceRouter
from core.knowledge.sql_source import SQLKnowledgeSource


class StubBackend:
    def execute(self, query, parameters=None):
        return []


def router():
    sources = KnowledgeSourceRegistry()
    source = SQLKnowledgeSource(StubBackend(), default_query="SELECT * FROM accounts WHERE customer_id = ?", aliases=("sqlite db",))
    source.name = "business_db"
    sources.register(source)
    return ResourceRouter(sources, build_fraud_investigation_graphs())


def test_routes_single_and_multiple_registered_resources():
    result = router().route("read from fraud graph")
    assert [item.name for item in result.selections] == ["fraud_graph"]
    result = router().route("customer graph, fraud graph and sqlite db for C1001")
    assert [item.name for item in result.selections] == ["customer_graph", "fraud_graph", "business_db"]
    assert len(result.graph_requests) == 2
    assert result.source_tasks[0]["parameters"] == ("C1001",)


def test_no_resource_preserves_default_and_unknown_is_controlled():
    assert router().route("hello there") is None
    with pytest.raises(ValueError, match="Unknown or unavailable"):
        router().route("read from payroll_graph")
