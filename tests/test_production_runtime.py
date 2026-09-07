import core.composition as composition
from core.contracts.identity import SecurityContext


def test_fake_composition_does_not_enable_local_rag_inference(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    calls = []

    class StubRAG:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(composition, "RAGPipeline", StubRAG)
    composition.create_agent()

    assert calls == [{"enable_inference": False}]


def test_security_context_actor_id_is_used_by_agent(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    from scripts.manual.demo_fixtures import create_demo_agent

    with create_demo_agent() as agent:
        result = agent.run(
            "Am I allowed to access customer_graph?",
            security_context=SecurityContext(actor_id="investigator"),
        )

    assert result.output == "customer_graph -> ALLOWED"
