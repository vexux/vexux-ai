import re
import sys
import types

from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from apps.fraud.workflow import FraudInvestigationWorkflow
from apps.fraud.demo import FRAUD_KNOWLEDGE_DIR
from apps.fraud.demo import create_demo_agent
from core.composition import create_agent
from core.contracts.observation import Observation
from core.tools.registry import ToolRegistry
from core.workflows.registry import WorkflowRegistry
from evaluation.rag import (
    DeterministicLexicalEmbedder,
    KNOWLEDGE_DIR,
    evaluate_rag,
)
from rag.chunker import TextChunker
from rag.loader import DocumentLoader
from rag.pipeline import RAGPipeline


EXPECTED_DOCUMENTS = {
    "fraud_investigation_policy.md",
    "alert_handling.md",
    "transaction_monitoring.md",
    "shared_device_guidelines.md",
}


def _pipeline():
    return RAGPipeline(
        enable_inference=False,
        documents_path=KNOWLEDGE_DIR,
        embedder=DeterministicLexicalEmbedder(),
        relevance_threshold=0.2,
    )


def test_fraud_composition_can_inject_the_application_corpus(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    agent = create_agent(rag_documents_path=KNOWLEDGE_DIR)

    assert agent.execution_manager.retrieval.loader.folder == KNOWLEDGE_DIR
    assert agent.execution_manager.retrieval._initialized is False


def test_fraud_knowledge_corpus_loads_all_documents_without_customer_records():
    documents = DocumentLoader(KNOWLEDGE_DIR).load()

    assert {document["name"] for document in documents} == EXPECTED_DOCUMENTS
    assert all(document["source"] == document["name"] for document in documents)
    for document in documents:
        assert document["title"]
        assert not re.search(r"\bC\d{4}\b|\bT\d{5}\b|ALERT\d+", document["content"])


def test_markdown_chunking_is_deterministic_and_preserves_section_metadata():
    document = next(
        document
        for document in DocumentLoader(KNOWLEDGE_DIR).load()
        if document["name"] == "shared_device_guidelines.md"
    )
    chunker = TextChunker(chunk_size=180, overlap=30)

    first = chunker.chunk(document["content"], metadata=document)
    second = chunker.chunk(document["content"], metadata=document)

    assert first == second
    assert len(first) > 1
    assert all(chunk["source"] == document["source"] for chunk in first)
    assert all(chunk["document_name"] == "shared_device_guidelines" for chunk in first)
    assert all(chunk["document_title"] == document["title"] for chunk in first)
    assert all(isinstance(chunk["chunk_index"], int) for chunk in first)
    assert {chunk["title"] for chunk in first} >= {
        "Investigative significance",
        "Legitimate and suspicious explanations",
        "Corroboration and assessment",
    }


def test_faiss_index_and_metadata_aware_retrieval_cover_each_knowledge_topic():
    pipeline = _pipeline()
    pipeline._ensure_initialized()

    cases = (
        (
            "What should investigators consider when customers share a device?",
            "shared_device_guidelines.md",
        ),
        (
            "How should an open high-severity alert be handled?",
            "alert_handling.md",
        ),
        (
            "What does transaction velocity mean and when should it trigger review?",
            "transaction_monitoring.md",
        ),
        (
            "What evidence should an investigator review before escalation?",
            "fraud_investigation_policy.md",
        ),
    )
    assert pipeline.store.index.ntotal > 0
    for query, expected_source in cases:
        results = pipeline.retrieve(query)
        assert results
        assert results[0]["source"] == expected_source
        assert results[0]["document"]
        assert results[0]["title"]
        assert isinstance(results[0]["chunk_index"], int)
        assert 0 <= results[0]["score"] <= 1


def test_unrelated_query_returns_no_context_and_synthesizes_no_answer():
    pipeline = _pipeline()
    unrelated_queries = (
        "What is the capital of Japan?",
        "How do I bake sourdough bread?",
        "What is the best espresso grind size and extraction time?",
    )

    for query in unrelated_queries:
        assert pipeline.retrieve(query) == []
        assert pipeline.ask(query) == (
            "No sufficiently relevant knowledge context was found to answer that question."
        )

    synthesizer = ResponseSynthesizer(model_gateway=None)
    response = synthesizer.synthesize(
        unrelated_queries[0],
        [
            Observation(
                success=False,
                output={"context_found": False, "results": []},
            )
        ],
    )
    assert "No sufficiently relevant knowledge context" in response


def test_no_context_cannot_be_overridden_by_a_model_fallback():
    class Gateway:
        def generate(self, prompt, **kwargs):
            raise AssertionError("No-context must not trigger a model-generated fallback.")

    response = ResponseSynthesizer(Gateway()).synthesize(
        "What policy applies?",
        [
            Observation(
                success=False,
                output={"context_found": False, "results": []},
            ),
            Observation(success=True, output="Unsupported generated answer."),
        ],
    )

    assert "No sufficiently relevant knowledge context" in response


def test_legacy_pipeline_ask_does_not_initialize_inference_when_retrieval_is_empty(
    monkeypatch,
):
    class Inference:
        def __init__(self):
            raise AssertionError("Inference must not initialize without retrieved context.")

    class EmptyRetriever:
        def retrieve(self, query, k):
            return []

    monkeypatch.setitem(
        sys.modules,
        "training.inference",
        types.SimpleNamespace(InferencePipeline=Inference),
    )
    pipeline = RAGPipeline(enable_inference=True)
    pipeline.retriever = EmptyRetriever()
    pipeline._initialized = True

    answer = pipeline.ask("What is unrelated?")

    assert "No sufficiently relevant knowledge context" in answer


def test_operational_and_mixed_customer_queries_remain_on_fraud_workflow():
    registry = WorkflowRegistry()
    registry.register(FraudInvestigationWorkflow.__new__(FraudInvestigationWorkflow))
    planner = Planner(
        model_gateway=None,
        tool_registry=ToolRegistry(),
        workflow_registry=registry,
    )

    for query, query_kind in (
        ("Investigate C1001", "investigation"),
        ("Show transactions for C1001", "transactions"),
        ("What alerts does C1001 have?", "alerts"),
        ("What connections does C1001 have?", "connections"),
        ("Compare C1001 and C1002", "comparison"),
    ):
        plan = planner.create_plan(query)
        assert len(plan.tasks) == 1, query
        assert plan.tasks[0].metadata["workflow"] == "fraud_investigation"
        assert plan.tasks[0].input["query_kind"] == query_kind

    mixed_plan = planner.create_plan(
        "Show transactions for C1001 and explain transaction velocity"
    )
    assert len(mixed_plan.tasks) == 2
    assert mixed_plan.tasks[0].metadata["workflow"] == "fraud_investigation"
    assert mixed_plan.tasks[1].metadata["capability"] == "retrieval"
    assert mixed_plan.tasks[1].depends_on == [mixed_plan.tasks[0].id]

    for query in (
        "What should an investigator consider when a customer shares a device with another customer?",
        "What does a shared device indicate in a fraud investigation?",
        "How should shared-device relationships be interpreted?",
        "What evidence should an investigator review before escalation?",
    ):
        policy_plan = planner.create_plan(query)
        assert len(policy_plan.tasks) == 1, query
        assert policy_plan.tasks[0].metadata["capability"] == "retrieval", query


def test_demo_uses_real_fraud_corpus_with_the_production_rag_pipeline():
    with create_demo_agent() as agent:
        rag = agent.execution_manager.retrieval
        assert isinstance(rag, RAGPipeline)
        assert rag.loader.folder == FRAUD_KNOWLEDGE_DIR
        rag.embedder = DeterministicLexicalEmbedder()
        rag.relevance_threshold = 0.2

        results = rag.retrieve(
            "What does a shared device indicate in a fraud investigation?"
        )

    assert results
    assert results[0]["source"] == "shared_device_guidelines.md"
    assert "investigative lead" in results[0]["document"].lower()


def test_end_to_end_generated_answers_are_copied_from_retrieved_context():
    cases = (
        (
            "What does a shared device indicate in a fraud investigation?",
            "shared_device_guidelines.md",
            "A shared-device relationship is an investigative lead",
        ),
        (
            "How should an open high-severity alert be handled?",
            "alert_handling.md",
            "An open high-severity alert warrants timely review under the applicable",
        ),
        (
            "What is transaction velocity: activity over a defined time window, and when should it trigger review?",
            "transaction_monitoring.md",
            "Transaction velocity describes activity over a defined time window",
        ),
        (
            "What evidence should an investigator review before escalation?",
            "fraud_investigation_policy.md",
            "source evidence is credible and",
        ),
    )

    class ContextCopyingGateway:
        def __init__(self, query, source, claim):
            self.query = query
            self.source = source
            self.claim = claim
            self.prompt = None

        def generate(self, prompt, **kwargs):
            self.prompt = prompt
            assert self.query in prompt
            assert self.source in prompt
            assert self.claim in prompt
            return self.claim

    for query, source, claim in cases:
        with create_demo_agent() as agent:
            rag = agent.execution_manager.retrieval
            assert isinstance(rag, RAGPipeline)
            rag.embedder = DeterministicLexicalEmbedder()
            rag.relevance_threshold = 0.2
            gateway = ContextCopyingGateway(query, source, claim)
            agent.response_synthesizer.model_gateway = gateway

            response = agent.run(query, user_id="investigator")

        assert response.success is True, query
        assert len(response.trace) == 1
        observation = response.trace[0]
        assert observation.metadata["capability"] == "retrieval"
        retrieved = observation.output["results"]
        assert retrieved
        assert any(item["source"] == source for item in retrieved)
        source_context = "\n".join(item["document"] for item in retrieved)
        assert claim in source_context
        assert gateway.prompt is not None
        assert claim in response.output
        assert f"Sources:\n- {source} — " in response.output


def test_mixed_request_executes_operational_workflow_then_grounded_policy_retrieval():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        rag = agent.execution_manager.retrieval
        calls = []

        def retrieve(query, k=None):
            calls.append(query)
            return [
                {
                    "document": "Transaction velocity measures activity over time.",
                    "score": 0.9,
                    "source": "transaction_monitoring.md",
                    "title": "Velocity and unusual activity",
                    "chunk_index": 0,
                }
            ]

        rag.retrieve = retrieve
        response = agent.run(
            "Show transactions for C1001 and explain transaction velocity",
            user_id="investigator",
        )

    assert response.success is True
    assert len(response.trace) == 2
    assert response.trace[0].metadata["workflow"] == "fraud_investigation"
    assert response.trace[1].output["context_found"] is True
    assert calls and "explain transaction velocity" in calls[0].lower()
    assert "transaction_monitoring.md" in response.output


def test_customer_transaction_query_does_not_call_rag():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        rag = agent.execution_manager.retrieval

        def reject_rag(query, k=None):
            raise AssertionError("Customer transaction questions must use the fraud workflow.")

        rag.retrieve = reject_rag
        response = agent.run("Show transactions for C1001", user_id="investigator")

    assert response.success is True
    assert "T1001" in response.output
    assert response.trace[0].metadata["workflow"] == "fraud_investigation"


def test_mixed_request_does_not_run_policy_retrieval_after_workflow_denial():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        rag = agent.execution_manager.retrieval
        calls = []
        rag.retrieve = lambda query, k=None: calls.append(query) or []

        response = agent.run(
            "Investigate C1001 and explain shared-device significance",
            user_id="support_user",
        )

    assert response.success is False
    assert response.metadata["authorization_denied"] is True
    assert calls == []


def test_rag_evaluation_covers_retrieval_and_routing_cases():
    report = evaluate_rag()

    assert report["total"] == 8
    assert report["passed"] == report["total"], report["results"]
    assert "evaluation only" in report["embedding"]


def test_response_synthesizer_uses_only_retrieved_source_metadata_for_citation():
    class Gateway:
        def generate(self, prompt, **kwargs):
            assert "Never derive or change a domain assessment" in prompt
            return "A shared device is an investigative lead."

    response = ResponseSynthesizer(Gateway()).synthesize(
        "What does a shared device indicate?",
        [
            Observation(
                success=True,
                output={
                    "context_found": True,
                    "results": [
                        {
                            "document": "A shared device is an investigative lead.",
                            "score": 0.8,
                            "source": "shared_device_guidelines.md",
                            "title": "Investigative significance",
                            "chunk_index": 0,
                        }
                    ],
                },
            )
        ],
    )

    assert response.endswith(
        "Sources:\n- shared_device_guidelines.md — Investigative significance (chunk 0)"
    )
