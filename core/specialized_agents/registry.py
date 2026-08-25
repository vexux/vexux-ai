from typing import Any, Dict, List

from core.contracts.orchestrator import SpecializedAgentContract


class SpecializedAgentRegistry:
    def __init__(self):
        self._agents: Dict[str, SpecializedAgentContract] = {}

    def register(self, agent: SpecializedAgentContract) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Specialized agent already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> SpecializedAgentContract:
        if name not in self._agents:
            raise KeyError(f"Specialized agent not found: {name}")
        return self._agents[name]

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def describe_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": agent.name,
                "description": agent.description,
            }
            for agent in self._agents.values()
        ]
