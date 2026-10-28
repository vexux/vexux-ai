import pytest

from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from agent.execution_manager import ExecutionManager
from core.contracts.execution import Task, AgentContext


def retrieval_task_with_graph(source, operation=None, params=None):
    input_data = {"query": "graph query", "source": source}
    if operation is not None:
        input_data["operation"] = operation
    if params is not None:
        input_data["params"] = params
    return Task(id="t-graph", description="graph op", input=input_data, metadata={"capability": "retrieval"})


def test_get_node_success():
    graphs = KnowledgeGraphRegistry()
    g = InMemoryKnowledgeGraph()
    graphs.register(g)
    g.add_node("n1", label="Person", properties={"name": "Alice"})

    manager = ExecutionManager(knowledge_graph_registry=graphs)

    task = retrieval_task_with_graph("inmemory", operation="get_node", params={"node_id": "n1"})
    res = manager.execute(task, AgentContext(request_id="r1"))

    assert res.success is True
    assert res.output["result"]["id"] == "n1"
    assert "evidence" in res.output
    assert res.output["evidence"].items[0].evidence_type == "graph_node"


def test_get_node_missing_fails():
    graphs = KnowledgeGraphRegistry()
    g = InMemoryKnowledgeGraph()
    graphs.register(g)

    manager = ExecutionManager(knowledge_graph_registry=graphs)

    task = retrieval_task_with_graph("inmemory", operation="get_node", params={"node_id": "missing"})
    res = manager.execute(task, AgentContext(request_id="r2"))

    assert res.success is False
    assert "Node not found" in (res.error or "")


def test_get_relationship_success_and_missing():
    graphs = KnowledgeGraphRegistry()
    g = InMemoryKnowledgeGraph()
    graphs.register(g)
    g.add_node("a")
    g.add_node("b")
    rel = g.add_relationship("a", "b", rel_type="knows")

    manager = ExecutionManager(knowledge_graph_registry=graphs)

    task = retrieval_task_with_graph("inmemory", operation="get_relationship", params={"rel_id": rel["id"]})
    res = manager.execute(task, AgentContext(request_id="r3"))
    assert res.success is True
    assert res.output["result"]["id"] == rel["id"]
    assert res.output["evidence"].items[0].evidence_type == "graph_relationship"

    # missing
    task2 = retrieval_task_with_graph("inmemory", operation="get_relationship", params={"rel_id": "rel:9999"})
    res2 = manager.execute(task2, AgentContext(request_id="r4"))
    assert res2.success is False
    assert "Relationship not found" in (res2.error or "")


def test_get_neighbors_success_and_direction_and_missing():
    graphs = KnowledgeGraphRegistry()
    g = InMemoryKnowledgeGraph()
    graphs.register(g)
    g.add_node("n1")
    g.add_node("n2")
    g.add_node("n3")
    g.add_relationship("n1", "n2", rel_type="r1")
    g.add_relationship("n3", "n1", rel_type="r2")

    manager = ExecutionManager(knowledge_graph_registry=graphs)

    task = retrieval_task_with_graph("inmemory", operation="get_neighbors", params={"node_id": "n1", "direction": "both"})
    res = manager.execute(task, AgentContext(request_id="r5"))
    assert res.success is True
    assert isinstance(res.output["results"], list)
    assert len(res.output["results"]) == 2
    assert all(item.get("direction") in ("outgoing", "incoming") for item in res.output["results"])

    # missing node
    task2 = retrieval_task_with_graph("inmemory", operation="get_neighbors", params={"node_id": "missing"})
    res2 = manager.execute(task2, AgentContext(request_id="r6"))
    assert res2.success is False
    assert "Node not found" in (res2.error or "")


def test_explicit_graph_request_with_no_registry_fails():
    # No registry configured on manager
    manager = ExecutionManager()
    task = retrieval_task_with_graph("inmemory", operation="get_node", params={"node_id": "x"})
    res = manager.execute(task, AgentContext(request_id="r7"))
    assert res.success is False
    # Accept either the explicit "capability unavailable" message or the controlled KeyError
    err = res.error or ""
    assert ("Knowledge graph capability unavailable" in err) or ("Unknown or unavailable knowledge source" in err) or ("not found" in err)


def test_no_silent_fallback_to_rag():
    # Ensure that requesting a graph when only RAG exists errors if graph missing
    # Configure manager with a fake RAG but no graph
    class FakeRAG:
        def retrieve(self, q, k=None):
            return [{"document": q}]

    manager = ExecutionManager(retrieval=FakeRAG())
    task = retrieval_task_with_graph("inmemory", operation="get_node", params={"node_id": "n1"})
    res = manager.execute(task, AgentContext(request_id="r8"))
    # Should be an unknown source error or graph unavailable error (controlled failure) — not routed to RAG
    assert res.success is False


if __name__ == "__main__":
    pytest.main([__file__])
