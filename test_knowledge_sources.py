import json

import pytest

from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.registry import KnowledgeSourceRegistry
from core.tools.registry import ToolRegistry
from rag.knowledge_source import RAGKnowledgeSource


class FakeKnowledgeSource:

    def __init__(self, name="fake", results=None, error=None):
        self._name = name
        self.results = results or []
        self.error = error
        self.calls = []

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "Provides deterministic test knowledge."

    @property
    def capabilities(self):
        return ["retrieval"]

    def retrieve(self, query, k=None):
        self.calls.append((query, k))
        if self.error:
            raise self.error
        return self.results if k is None else self.results[:k]


def retrieval_task(query, **extra_input):
    return Task(
        id="task-1",
        description="Retrieve context",
        input={"query": query, **extra_input},
        metadata={"capability": "retrieval"},
    )


def test_knowledge_source_registry_registers_and_describes_sources():
    registry = KnowledgeSourceRegistry()
    source = FakeKnowledgeSource("primary")

    registry.register(source)

    assert registry.get() is source
    assert registry.get("primary") is source
    assert registry.describe_sources() == [{
        "name": "primary",
        "description": "Provides deterministic test knowledge.",
        "capabilities": ["retrieval"],
    }]

    with pytest.raises(KeyError, match="Knowledge source not found: missing"):
        registry.get("missing")

    with pytest.raises(ValueError, match="already registered"):
        registry.register(source)


def test_rag_knowledge_source_delegates_to_pipeline_retrieve():
    class Pipeline:
        def __init__(self):
            self.calls = []

        def retrieve(self, query, k=None):
            self.calls.append((query, k))
            return [{"score": 0.9, "document": query}]

    pipeline = Pipeline()
    source = RAGKnowledgeSource(pipeline)

    assert source.retrieve("EC2") == [{"score": 0.9, "document": "EC2"}]
    assert source.retrieve("Python", k=2) == [{"score": 0.9, "document": "Python"}]
    assert pipeline.calls == [("EC2", None), ("Python", 2)]
    assert source.name == "rag"
    assert source.capabilities == ["retrieval"]


def test_execution_manager_uses_registered_knowledge_source():
    source = FakeKnowledgeSource(results=[{"score": 0.9, "document": "EC2"}])
    registry = KnowledgeSourceRegistry()
    registry.register(source)
    manager = ExecutionManager(knowledge_source_registry=registry)

    result = manager.execute(
        retrieval_task("What is EC2?", top_k=1),
        AgentContext(request_id="request-1"),
    )

    assert result.success is True
    assert result.output == {
        "query": "What is EC2?",
        "results": [{"score": 0.9, "document": "EC2"}],
        "context_found": True,
    }
    assert source.calls == [("What is EC2?", 1)]


def test_unknown_or_failing_knowledge_source_is_controlled_failure():
    registry = KnowledgeSourceRegistry()
    registry.register(FakeKnowledgeSource(error=RuntimeError("source unavailable")))
    manager = ExecutionManager(knowledge_source_registry=registry)

    unknown = manager.execute(
        retrieval_task("EC2", source="missing"),
        AgentContext(request_id="request-2"),
    )
    failed = manager.execute(
        retrieval_task("EC2"),
        AgentContext(request_id="request-3"),
    )

    assert unknown.success is False
    assert unknown.error == "'Knowledge source not found: missing'"
    assert failed.success is False
    assert failed.error == "source unavailable"


def test_agent_retrieval_task_uses_default_registered_source():
    class Gateway:
        def generate(self, prompt, **kwargs):
            if "structured planning component" in prompt:
                return json.dumps({"tasks": [{
                    "id": "task-1",
                    "description": "Retrieve context",
                    "capability": "retrieval",
                    "input": {"query": "What is EC2?"},
                }]})
            return "Grounded EC2 answer"

    source = FakeKnowledgeSource(results=[{"score": 0.9, "document": "EC2 context"}])
    knowledge_sources = KnowledgeSourceRegistry()
    knowledge_sources.register(source)
    gateway = Gateway()
    agent = Agent(
        execution_manager=ExecutionManager(
            knowledge_source_registry=knowledge_sources,
        ),
        planner=Planner(gateway, ToolRegistry()),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=ResponseSynthesizer(gateway),
    )

    response = agent.run("What is EC2?")

    assert response.success is True
    assert response.output == "Grounded EC2 answer"
    assert source.calls == [("What is EC2?", None)]


def test_second_source_can_be_selected_without_core_source_logic():
    primary = FakeKnowledgeSource("primary", results=[{"document": "primary"}])
    secondary = FakeKnowledgeSource("secondary", results=[{"document": "secondary"}])
    registry = KnowledgeSourceRegistry()
    registry.register(primary)
    registry.register(secondary)
    manager = ExecutionManager(knowledge_source_registry=registry)

    result = manager.execute(
        retrieval_task("query", source="secondary"),
        AgentContext(request_id="request-4"),
    )

    assert result.success is True
    assert result.output["results"] == [{"document": "secondary"}]
    assert primary.calls == []
    assert secondary.calls == [("query", None)]
