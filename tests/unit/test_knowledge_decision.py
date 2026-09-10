import pytest

from core.knowledge.decision import KnowledgeDecision
from core.contracts.knowledge import KnowledgeRequest
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.graph_registry import KnowledgeGraphRegistry


class FakeRAG:
    def retrieve(self, q, k=None):
        return [{"document": q}]


class FakeSource:
    def __init__(self, name="primary"):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "fake"

    @property
    def capabilities(self):
        return ["retrieval"]

    def retrieve(self, query, k=None):
        return [{"document": query}]


class FakeGraph:
    def __init__(self, name="graph1"):
        self._name = name

    @property
    def name(self):
        return self._name


def test_generic_request_prefers_rag_over_registered_structured_source():
    registry = KnowledgeSourceRegistry()
    registry.register(FakeSource("business_db"))
    decision = KnowledgeDecision(rag=FakeRAG(), knowledge_source_registry=registry)

    req = decision.create_request("hey")

    assert req.kind == "rag"
    assert req.source == "rag"


def test_knowledge_request_contract_can_be_created():
    req = KnowledgeRequest(kind="rag", query="What is EC2?", source="rag")
    assert req.kind == "rag"
    assert req.query == "What is EC2?"


def test_rag_decision_when_available_and_explicit():
    decision = KnowledgeDecision(rag=FakeRAG())
    req = decision.create_request("query", explicit_source="rag")
    assert req.kind == "rag"
    assert req.source == "rag"


def test_rag_decision_when_unavailable_raises():
    decision = KnowledgeDecision(rag=None)
    with pytest.raises(ValueError, match="rag"):
        decision.create_request("q", explicit_source="rag")


def test_registered_knowledge_source_is_selected_by_default():
    registry = KnowledgeSourceRegistry()
    registry.register(FakeSource("primary"))
    decision = KnowledgeDecision(knowledge_source_registry=registry)

    req = decision.create_request("select * from items")
    assert req.kind == "knowledge_source"
    assert req.source == "primary"


def test_explicit_registered_source_selection():
    registry = KnowledgeSourceRegistry()
    registry.register(FakeSource("primary"))
    registry.register(FakeSource("secondary"))
    decision = KnowledgeDecision(knowledge_source_registry=registry)

    req = decision.create_request("q", explicit_source="secondary")
    assert req.kind == "knowledge_source"
    assert req.source == "secondary"


def test_unknown_explicit_source_raises_and_does_not_fallback():
    registry = KnowledgeSourceRegistry()
    registry.register(FakeSource("primary"))
    decision = KnowledgeDecision(knowledge_source_registry=registry)

    with pytest.raises(KeyError):
        # request an explicitly-named graph that does not exist — must error
        decision.create_request("q", explicit_source="graph-missing")


def test_graph_selection_when_registered():
    graphs = KnowledgeGraphRegistry()
    graphs.register(FakeGraph("g1"))
    decision = KnowledgeDecision(knowledge_graph_registry=graphs)

    req = decision.create_request("find node", explicit_source="g1")
    assert req.kind == "graph"
    assert req.source == "g1"


def test_explicit_graph_missing_raises():
    graphs = KnowledgeGraphRegistry()
    decision = KnowledgeDecision(knowledge_graph_registry=graphs)

    with pytest.raises(KeyError):
        decision.create_request("query", explicit_source="g-missing")


def test_no_capabilities_available_raises():
    decision = KnowledgeDecision()
    with pytest.raises(RuntimeError):
        decision.create_request("query")
