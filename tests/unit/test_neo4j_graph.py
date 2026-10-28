import pytest

from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph


class FakeRecord(dict):
    pass


class FakeResult:
    def __init__(self, records):
        self.records = records

    def single(self):
        return self.records[0] if self.records else None

    def __iter__(self):
        return iter(self.records)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return self.responses.pop(0)


class FakeDriver:
    def __init__(self, responses):
        self.session_instance = FakeSession(responses)

    def session(self, **kwargs):
        return self.session_instance


def node(node_id, label="Person", **properties):
    return {"id": node_id, "label": label, "properties": {"id": node_id, **properties}}


def rel(rel_id, source, target, rel_type="knows"):
    return {"id": rel_id, "type": rel_type, "properties": {"id": rel_id}}


def graph(responses):
    return Neo4jKnowledgeGraph(
        "bolt://localhost",
        "neo4j",
        "secret",
        name="customer_graph",
        driver=FakeDriver(responses),
    )


def test_adapter_maps_node_and_parameterizes_id():
    driver_responses = [FakeResult([FakeRecord(n=node("n1"))])]
    g = graph(driver_responses)
    assert g.get_node("n1")["id"] == "n1"
    query, params = g._driver.session_instance.calls[0]
    assert "$node_id" in query
    assert "n1" not in query
    assert params == {"node_id": "n1"}


def test_adapter_maps_relationship_and_neighbors():
    relationship = rel("r1", "n1", "n2")
    g = graph([
        FakeResult([FakeRecord(source=node("n1"), target=node("n2"), r=relationship)]),
        FakeResult([FakeRecord(source=node("n1"), node=node("n2"), r=relationship)]),
    ])
    assert g.get_relationship("r1")["source"] == "n1"
    neighbors = g.get_neighbors("n1")
    assert neighbors[0]["node"]["id"] == "n2"
    assert neighbors[0]["direction"] == "outgoing"


def test_missing_node_and_connection_errors_are_normalized():
    g = graph([FakeResult([])])
    with pytest.raises(KeyError, match="Node not found"):
        g.get_node("missing")

    class BrokenDriver:
        def session(self, **kwargs):
            raise OSError("password=secret")

    broken = Neo4jKnowledgeGraph("bolt://localhost", "neo4j", "secret", driver=BrokenDriver())
    with pytest.raises(RuntimeError, match="Neo4j query failed") as error:
        broken.get_node("n1")
    assert "secret" not in str(error.value)


def test_registry_accepts_heterogeneous_graph_backends():
    registry = KnowledgeGraphRegistry()
    registry.register(graph([FakeResult([FakeRecord(n=node("n1"))])]))
    registry.register(type("MemoryGraph", (), {"name": "fraud_graph"})())
    assert registry.get("customer_graph").name == "customer_graph"
    assert registry.get("fraud_graph").name == "fraud_graph"


def test_invalid_relationship_type_is_rejected():
    g = graph([])
    with pytest.raises(ValueError):
        g.add_relationship("n1", "n2", rel_type="bad} MATCH (n)")

