from apps.fraud.demo import create_demo_agent
from types import SimpleNamespace


def test_demo_fixture_registers_reference_resources_and_policy(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    with create_demo_agent() as agent:
        resources = agent.resource_router._resources()
        assert [resource.name for resource in resources] == [
            "customer_graph",
            "fraud_graph",
            "business_db",
        ]

        investigator = agent.run(
            "am I allowed to access customer_graph and fraud_graph?",
            user_id="investigator",
        )
        support_user = agent.run(
            "am I allowed to access customer_graph and fraud_graph?",
            user_id="support_user",
        )

        assert investigator.output == "customer_graph -> ALLOWED\nfraud_graph -> ALLOWED"
        assert support_user.output == "customer_graph -> ALLOWED\nfraud_graph -> DENIED"


def test_demo_single_graph_query_executes_through_graph_resource(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    with create_demo_agent() as agent:
        result = agent.run(
            "Give me information about C1001 from the customer graph.",
            user_id="investigator",
        )

    assert result.success is True
    assert any(
        observation.metadata.get("source") == "customer_graph"
        for observation in result.trace
    )


def test_generic_agent_initialization_does_not_import_demo_fixture(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    from core.composition import create_agent

    agent = create_agent()
    assert agent.resource_router.knowledge_graph_registry is None


def test_demo_provider_defaults_only_when_environment_is_absent(monkeypatch):
    observed = []
    fake_agent = SimpleNamespace(
        resource_router=SimpleNamespace(),
        execution_manager=SimpleNamespace(),
        knowledge_graph_registry=None,
    )

    def fake_create_agent():
        observed.append(__import__("os").environ.get("MODEL_PROVIDER"))
        return fake_agent

    monkeypatch.setattr("apps.fraud.demo.composition.create_agent", fake_create_agent)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    with create_demo_agent():
        pass
    assert observed == ["fake"]
    assert "MODEL_PROVIDER" not in __import__("os").environ


def test_demo_provider_respects_explicit_environment(monkeypatch):
    observed = []
    fake_agent = SimpleNamespace(
        resource_router=SimpleNamespace(),
        execution_manager=SimpleNamespace(),
        knowledge_graph_registry=None,
    )

    def fake_create_agent():
        observed.append(__import__("os").environ.get("MODEL_PROVIDER"))
        return fake_agent

    monkeypatch.setattr("apps.fraud.demo.composition.create_agent", fake_create_agent)
    monkeypatch.setenv("MODEL_PROVIDER", "qwen")
    with create_demo_agent():
        pass
    assert observed == ["qwen"]
    assert __import__("os").environ["MODEL_PROVIDER"] == "qwen"
