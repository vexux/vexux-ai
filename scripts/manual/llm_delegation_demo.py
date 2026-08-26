"""Manual demo: show orchestrator using an LLM-based delegation planner.

Run from the repository root:
python scripts/manual/llm_delegation_demo.py

This demo uses a FakeModelGateway that returns a predefined JSON delegation plan.
"""

import json
import sys
from pathlib import Path
import os

# Ensure repository root is on sys.path so local packages can be imported when running
# the script directly from the repo root or scripts/manual.
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from core.orchestrator import Orchestrator
from core.contracts.response import AgentResponse
from core.specialized_agents.registry import SpecializedAgentRegistry
from core.specialized_agents.llm_delegation_planner import LLMDelegationPlanner
from core.specialized_agents.planner import DelegationPlanner


class FakeModelGateway:
    def __init__(self, payload: str):
        self.payload = payload
        self.invoked = False

    def generate(self, prompt: str, max_new_tokens: int = 256, do_sample: bool = False):
        # Mark that the model was invoked so the demo can report it
        self.invoked = True
        print("--- MODEL PROMPT (truncated) ---")
        print(prompt[:1000])
        print("--- END PROMPT ---")
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


def main():
    # Preconfigured model response: two delegations (research -> analysis depends on research)
    model_response = json.dumps(
        {
            "delegations": [
                {"id": "research", "agent": "research", "request": "Find relevant documents about X"},
                {"id": "analysis", "agent": "analysis", "request": {"from_task": "research", "path": "output"}, "depends_on": ["research"]},
            ]
        }
    )

    gateway = FakeModelGateway(model_response)
    base_agent = BaseAgent()

    registry = SpecializedAgentRegistry()
    registry.register(DummySpecializedAgent("research"))
    registry.register(DummySpecializedAgent("analysis"))

    # Build a planner but only pass it to the orchestrator when the environment toggle is enabled.
    llm_planner = LLMDelegationPlanner(model_gateway=gateway, base_planner=DelegationPlanner(registry), specialized_agent_registry=registry, max_delegations=4)

    enable_env = os.getenv("ENABLE_AUTONOMOUS_DELEGATION", "").lower() in ("1", "true", "yes")
    print(f"ENABLE_AUTONOMOUS_DELEGATION environment flag: {enable_env}")

    if enable_env:
        orchestrator = Orchestrator(base_agent, specialized_agent_registry=registry, delegation_planner=llm_planner)
    else:
        orchestrator = Orchestrator(base_agent, specialized_agent_registry=registry)

    print("Running orchestrator... (autonomous planner invoked only when enabled)")
    result = orchestrator.run({"query": "Investigate case X"})

    # Report whether the LLM planner was actually invoked (FakeModelGateway sets .invoked)
    invoked = getattr(gateway, "invoked", False)
    print(f"LLMDelegationPlanner invoked: {invoked}")

    # If autonomous planning was used, print delegation summary (count and agent names)
    if invoked and isinstance(result.output, list):
        delegation_count = len(result.output)
        agent_names = [getattr(item, "target_agent", None) for item in result.output]
        print(f"Autonomous delegation count: {delegation_count}")
        print(f"Delegated agents: {agent_names}")

    print("SUCCESS:", result.success)
    print("ERROR:", result.error)
    print("METADATA:", result.metadata)
    print("--- Delegation Results ---")
    if isinstance(result.output, list):
        for item in result.output:
            print(f"id={item.delegation_id}, target={item.target_agent}, success={item.success}, output={item.output}, error={item.error}, metadata={item.metadata}")
    else:
        print(result.output)


if __name__ == "__main__":
    main()
