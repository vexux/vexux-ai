import pytest
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph


def test_add_and_get_node():
    g = InMemoryKnowledgeGraph()
    node = g.add_node("n1", label="Person", properties={"name": "Alice"})
    assert node["id"] == "n1"
    got = g.get_node("n1")
    assert got["properties"]["name"] == "Alice"


def test_duplicate_node_raises():
    g = InMemoryKnowledgeGraph()
    g.add_node("n1")
    with pytest.raises(ValueError):
        g.add_node("n1")


def test_add_relationship_and_neighbors():
    g = InMemoryKnowledgeGraph()
    g.add_node("a")
    g.add_node("b")
    rel = g.add_relationship("a", "b", rel_type="knows")
    assert rel["source"] == "a"
    neighbors = g.get_neighbors("a", direction="outgoing")
    assert any(n["node"]["id"] == "b" for n in neighbors)


def test_duplicate_relationship_raises():
    g = InMemoryKnowledgeGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_relationship("a", "b", rel_type="knows")
    with pytest.raises(ValueError):
        g.add_relationship("a", "b", rel_type="knows")


def test_remove_relationship_and_node_cleanup():
    g = InMemoryKnowledgeGraph()
    g.add_node("a")
    g.add_node("b")
    rel = g.add_relationship("a", "b")
    r_id = rel["id"]
    g.remove_relationship(r_id)
    with pytest.raises(KeyError):
        g.get_relationship(r_id)
    # now safe to remove nodes
    g.remove_node("a")
    g.remove_node("b")


def test_remove_node_with_relationships_raises():
    g = InMemoryKnowledgeGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_relationship("a", "b")
    with pytest.raises(ValueError):
        g.remove_node("a")
