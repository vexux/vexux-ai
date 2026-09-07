import json

from core.orchestrator import Orchestrator
from core.contracts.response import AgentResponse
from core.specialized_agents.registry import SpecializedAgentRegistry
from core.specialized_agents.llm_delegation_planner import LLMDelegationPlanner
from core.specialized_agents.planner import DelegationPlanner


class FakeModelGateway:
    def __init__(self, payload: str):
        self.payload = payload

    def generate(self, prompt: str, max_new_tokens: int = 256, do_sample: bool = False):
        # ignore prompt, return preconfigured payload
        return self.payload


class BaseAgent:
    def run(self, query, session_id=None, user_id=None):
        return AgentResponse(success=True, output=f"general:{query}")


class DummySpecializedAgent:
    def __init__(self, name, description=None):
        self.name = name
        self.description = description or f"{name} specialized agent"

    def run(self, request, session_id=None, user_id=None):
        payload = request.get("query") if isinstance(request, dict) else request
        return AgentResponse(success=True, output=f"{self.name}:{payload}")


def test_llm_delegation_happy_path():
    # model returns a valid JSON plan proposing two delegations: research -> analysis(depends_on research)
    model_response = json.dumps(
        {
            "delegations": [
                {"id": "research", "agent": "research", "request": "Find papers"},
                {"id": "analysis", "agent": "analysis", "request": {"from_task": "research", "path": "output"}, "depends_on": ["research"]},
            ]
        }
    )
    gateway = FakeModelGateway(model_response)

    base_agent = BaseAgent()
    registry = SpecializedAgentRegistry()
    registry.register(DummySpecializedAgent("research"))
    registry.register(DummySpecializedAgent("analysis"))

    llm_planner = LLMDelegationPlanner(model_gateway=gateway, base_planner=DelegationPlanner(registry), specialized_agent_registry=registry, max_delegations=4)
    orchestrator = Orchestrator(base_agent, specialized_agent_registry=registry, delegation_planner=llm_planner)

    result = orchestrator.run({"query": "Investigate X"})
    assert result.success is True
    assert isinstance(result.output, list)
    assert [item.delegation_id for item in result.output] == ["research", "analysis"]
    assert result.output[0].target_agent == "research"
    assert result.output[1].target_agent == "analysis"


def test_llm_delegation_invalid_json_fails():
    gateway = FakeModelGateway("not a json")
    base_agent = BaseAgent()
    registry = SpecializedAgentRegistry()
    registry.register(DummySpecializedAgent("research"))

    llm_planner = LLMDelegationPlanner(model_gateway=gateway, base_planner=DelegationPlanner(registry), specialized_agent_registry=registry)
    orchestrator = Orchestrator(base_agent, specialized_agent_registry=registry, delegation_planner=llm_planner)

    result = orchestrator.run({"query": "Investigate Y"})
    assert result.success is False
    assert "Model returned invalid JSON" in result.error


def test_llm_delegation_too_many_delegations_rejected():
    # model returns more than allowed delegations
    payload = {"delegations": [{"id": f"d{i}", "agent": "research", "request": "x"} for i in range(6)]}
    gateway = FakeModelGateway(json.dumps(payload))

    base_agent = BaseAgent()
    registry = SpecializedAgentRegistry()
    registry.register(DummySpecializedAgent("research"))

    llm_planner = LLMDelegationPlanner(model_gateway=gateway, base_planner=DelegationPlanner(registry), specialized_agent_registry=registry, max_delegations=4)
    orchestrator = Orchestrator(base_agent, specialized_agent_registry=registry, delegation_planner=llm_planner)

    result = orchestrator.run({"query": "Investigate Z"})
    assert result.success is False
    assert "exceeds the allowed maximum" in result.error
