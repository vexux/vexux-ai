import json

from agent.execution_manager import ExecutionManager
from core.audit_logger import clear_events, get_events
from core.config import load_config_from_env
from core.contracts.execution import AgentContext, Task
from core.contracts.response import AgentResponse
from apps.fraud.composition import (
    create_fraud_investigation_fixture,
    create_fraud_investigation_request,
)
from core.model_gateway.gateway import ModelGateway
from core.orchestrator import Orchestrator
from core.policy.default import DefaultPolicy, PolicyDecision
from core.security.redaction import redact_sensitive_data
from core.specialized_agents.llm_delegation_planner import LLMDelegationPlanner
from core.specialized_agents.planner import DelegationPlanner
from core.specialized_agents.registry import SpecializedAgentRegistry


class ScenarioPolicy(DefaultPolicy):
    def __init__(self, denied_resources=None):
        super().__init__()
        self.denied_resources = denied_resources or set()

    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if (resource_type, resource_name) in self.denied_resources:
            return PolicyDecision(False, "denied", "scenario_policy")
        return PolicyDecision(True, policy_name="scenario_policy")


def _multi_graph_task():
    request = create_fraud_investigation_request(
        "Investigate customer C1001 and identify their associated accounts, fraud cases, and devices.",
        customer_id="C1001",
        device_id="D500",
    )
    return Task(
        id="integration-multigraph",
        description="secured investigation",
        input={
            "query": request.query,
            "graph_requests": request.as_dict_list(),
            "customer_id": "C1001",
        },
        metadata={"capability": "retrieval"},
    )


def test_authorized_multigraph_investigation_and_audit():
    clear_events()
    manager = ExecutionManager(
        knowledge_graph_registry=create_fraud_investigation_fixture(),
        policy=ScenarioPolicy(),
    )

    result = manager.execute(
        _multi_graph_task(),
        AgentContext(request_id="integration-authorized", user_id="investigator"),
    )

    assert result.success
    assert "Customer C1001 owns accounts A100, A101." in result.output["facts"]
    assert "The fraud graph associates C1001 with case F900." in result.output["facts"]
    assert "Customer C1001 is associated with device D500." in result.output["facts"]
    assert "Device D500 is also associated with customer C2001." in result.output["facts"]
    assert "fraud" not in " ".join(result.output["facts"]).lower().replace("fraud graph", "")

    events = get_events()
    graph_names = {event.resource_name for event in events}
    assert {"customer_graph", "fraud_graph"} <= graph_names
    assert {event.event_type for event in events} >= {
        "request_started",
        "request_completed",
        "authorization_allowed",
        "task_started",
        "task_completed",
        "resource_accessed",
    }
    assert any(
        event.resource_name == "multi_graph" and event.action == "aggregate"
        for event in events
    )
    assert all("api_key" not in repr(event).lower() for event in events)


def test_unauthorized_multigraph_fails_before_graph_execution():
    clear_events()
    manager = ExecutionManager(
        knowledge_graph_registry=create_fraud_investigation_fixture(),
        policy=ScenarioPolicy({("knowledge_graph", "fraud_graph")}),
    )

    result = manager.execute(
        _multi_graph_task(),
        AgentContext(request_id="integration-denied", user_id="support_user"),
    )

    assert not result.success
    assert "Unauthorized access to knowledge graph: fraud_graph" in result.error
    events = get_events()
    assert any(
        event.event_type == "authorization_denied"
        and event.resource_name == "fraud_graph"
        for event in events
    )
    assert not any(
        event.event_type == "task_completed"
        and event.resource_name == "fraud_graph"
        for event in events
    )


class CountingGateway:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return self.payload


class DelegatingAgent:
    def __init__(self):
        self.policy = DefaultPolicy()
        self.calls = 0

    def run(self, query, session_id=None, user_id=None):
        self.calls += 1
        return AgentResponse(success=True, output=f"general:{query}")


class RecordingSpecializedAgent:
    def __init__(self, name):
        self.name = name
        self.description = f"{name} integration agent"
        self.calls = 0

    def run(self, request, session_id=None, user_id=None):
        self.calls += 1
        return AgentResponse(success=True, output=f"{self.name}:done")


def test_autonomous_delegation_happy_path_calls_provider_once_and_audits():
    clear_events()
    gateway = CountingGateway(
        json.dumps(
            {
                "delegations": [
                    {"id": "research-1", "agent": "research", "request": "Find evidence"},
                ]
            }
        )
    )
    agent = DelegatingAgent()
    specialized = RecordingSpecializedAgent("research")
    registry = SpecializedAgentRegistry()
    registry.register(specialized)
    planner = LLMDelegationPlanner(
        model_gateway=gateway,
        base_planner=DelegationPlanner(registry),
        specialized_agent_registry=registry,
    )

    result = Orchestrator(
        agent,
        specialized_agent_registry=registry,
        delegation_planner=planner,
    ).run({"query": "Investigate synthetic case"})

    assert result.success
    assert gateway.calls == 1
    assert specialized.calls == 1
    assert result.metadata["orchestration_id"]
    assert any(event.event_type == "delegation_started" for event in get_events())
    assert any(event.event_type == "delegation_completed" for event in get_events())


def test_autonomous_delegation_invalid_plan_does_not_execute_agent():
    gateway = CountingGateway("not valid json")
    agent = DelegatingAgent()
    specialized = RecordingSpecializedAgent("research")
    registry = SpecializedAgentRegistry()
    registry.register(specialized)
    planner = LLMDelegationPlanner(
        model_gateway=gateway,
        base_planner=DelegationPlanner(registry),
        specialized_agent_registry=registry,
    )

    result = Orchestrator(
        agent,
        specialized_agent_registry=registry,
        delegation_planner=planner,
    ).run({"query": "Invalid synthetic plan"})

    assert not result.success
    assert "Model returned invalid JSON" in result.error
    assert gateway.calls == 1
    assert specialized.calls == 0
    assert agent.calls == 0


def test_fake_gateway_and_redaction_remain_provider_independent(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    config = load_config_from_env()
    assert config.model_provider == "fake"
    gateway = ModelGateway(__import__("models.providers.fake", fromlist=["FakeProvider"]).FakeProvider())
    assert gateway.generate("ordinary prompt").startswith("FAKE_RESPONSE:")
    safe = redact_sensitive_data(
        {
            "authorization": "Bearer synthetic-token",
            "details": "api_key=synthetic-key",
        }
    )
    assert "synthetic-token" not in repr(safe)
    assert "synthetic-key" not in repr(safe)


def test_persistent_memory_is_explicit_and_scoped(tmp_path):
    from core.memory.sqlite_memory import SQLiteMemory

    memory = SQLiteMemory(str(tmp_path / "integration-memory.db"))
    memory.store("case-a", "synthetic note")
    assert len(memory.retrieve("case-a", "synthetic")) == 1
    assert memory.retrieve("case-b") == []
