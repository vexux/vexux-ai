from agent.execution_manager import ExecutionManager
from core.contracts.execution import Task
from core.contracts.execution import AgentContext


class FakeRAG:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, k=None):
        self.calls.append((query, k))
        return [{"document": query}]


class FakeSource:
    def __init__(self, name="primary"):
        self._name = name
        self.calls = []

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
        self.calls.append((query, k))
        return [{"document": query}]


def retrieval_task(query, **extra_input):
    return Task(id="task-1", description="Retrieve context", input={"query": query, **extra_input}, metadata={"capability": "retrieval"})


def test_explicit_rag_selection_routes_to_rag_pipeline():
    rag = FakeRAG()
    manager = ExecutionManager(retrieval=rag)

    result = manager.execute(retrieval_task("EC2", source="rag"), AgentContext(request_id="r1"))

    assert result.success is True
    assert result.output["results"] == [{"document": "EC2"}]
    assert rag.calls == [("EC2", None)]


def test_explicit_unknown_source_returns_controlled_failure():
    manager = ExecutionManager(retrieval=FakeRAG())

    res = manager.execute(retrieval_task("EC2", source="missing"), AgentContext(request_id="r2"))

    assert res.success is False
    assert "Unknown or unavailable knowledge source" in (res.error or "") or "not found" in (res.error or "")