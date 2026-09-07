import pytest

from agent.decision import DecisionMaker, DecisionType
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.response_synthesizer import ResponseSynthesizer
from core.contracts.execution import AgentContext, Task
from core.contracts.observation import Observation
from rag.pipeline import RAGPipeline


class FakeRetrieval:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    def retrieve(self, query, k=3):
        self.calls.append((query, k))
        if self.error:
            raise self.error
        return self.results


class AskOnlyRetrieval:
    def ask(self, query):
        return f"Answer for {query}"


def retrieval_task(query, top_k=None):
    task_input = {"query": query}
    if top_k is not None:
        task_input["top_k"] = top_k
    return Task(
        id="task-1",
        description="Retrieve context",
        input=task_input,
        metadata={"capability": "retrieval"},
    )


def test_rag_pipeline_retrieve_filters_by_existing_similarity_score():
    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.top_k = 3
    pipeline.relevance_threshold = 0.8
    pipeline.retriever = FakeRetrieval([
        {"score": 0.95, "document": "relevant"},
        {"score": 0.2, "document": "irrelevant"},
    ])

    results = pipeline.retrieve("query")

    assert results == [{"score": 0.95, "document": "relevant"}]
    assert pipeline.retriever.calls == [("query", 3)]


def test_execution_manager_returns_structured_retrieval_result():
    retrieval = FakeRetrieval([
        {"score": 0.91, "document": "EC2 context"},
    ])
    manager = ExecutionManager(retrieval=retrieval)

    result = manager.execute(
        retrieval_task("What is EC2?", top_k=5),
        AgentContext(request_id="request-1"),
    )

    assert result.success is True
    assert result.output == {
        "query": "What is EC2?",
        "results": [{"score": 0.91, "document": "EC2 context"}],
        "context_found": True,
    }
    assert result.metadata["capability"] == "retrieval"
    assert retrieval.calls == [("What is EC2?", 5)]


def test_retrieval_no_result_is_distinct_failure():
    manager = ExecutionManager(retrieval=FakeRetrieval([]))

    result = manager.execute(
        retrieval_task("Unknown topic"),
        AgentContext(request_id="request-2"),
    )

    assert result.success is False
    assert result.output["context_found"] is False
    assert result.output["results"] == []
    assert "No sufficiently relevant" in result.error


def test_retrieval_exception_becomes_controlled_failure():
    manager = ExecutionManager(
        retrieval=FakeRetrieval(error=RuntimeError("vector store unavailable"))
    )

    result = manager.execute(
        retrieval_task("What is EC2?"),
        AgentContext(request_id="request-3"),
    )

    assert result.success is False
    assert result.output is None
    assert result.error == "vector store unavailable"


def test_legacy_ask_only_retrieval_remains_supported():
    manager = ExecutionManager(retrieval=AskOnlyRetrieval())

    result = manager.execute(
        retrieval_task("What is Python?"),
        AgentContext(request_id="request-4"),
    )

    assert result.success is True
    assert result.output == "Answer for What is Python?"


def test_retrieval_failure_flows_through_observer_and_decision_maker():
    manager = ExecutionManager(
        retrieval=FakeRetrieval(error=RuntimeError("retrieval failed"))
    )
    task = retrieval_task("What is EC2?")
    result = manager.execute(task, AgentContext(request_id="request-5"))
    observation = Observer().observe(result, task)

    assert observation.success is False
    assert observation.error == "retrieval failed"
    assert DecisionMaker().decide(observation) == DecisionType.REPLAN


def test_invalid_top_k_is_controlled_failure():
    manager = ExecutionManager(retrieval=FakeRetrieval())

    result = manager.execute(
        retrieval_task("What is EC2?", top_k=0),
        AgentContext(request_id="request-6"),
    )

    assert result.success is False
    assert "top_k" in result.error


def test_structured_single_retrieval_result_is_synthesized():
    class Gateway:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return "Grounded EC2 answer"

    gateway = Gateway()
    result = ResponseSynthesizer(gateway).synthesize(
        "What is EC2?",
        [
            Observation(
                success=True,
                output={
                    "query": "What is EC2?",
                    "results": [{
                        "score": 0.9,
                        "document": "EC2 provides compute capacity.",
                    }],
                    "context_found": True,
                },
            )
        ],
    )

    assert result == "Grounded EC2 answer"
    assert "retrieved context" in gateway.prompts[0]
