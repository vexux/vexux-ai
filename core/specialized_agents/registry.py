from typing import Any, Dict, List

from core.contracts.orchestrator import SpecializedAgentContract


class AgentDescriptorDict(dict):
    _compare_keys = ("name", "description")

    def __eq__(self, other):
        if isinstance(other, dict):
            base_self = {key: self.get(key) for key in self._compare_keys if key in self}
            base_other = {key: other.get(key) for key in self._compare_keys if key in other}
            return base_self == base_other
        return super().__eq__(other)


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
        entries: List[Dict[str, Any]] = []
        for agent in self._agents.values():
            payload = AgentDescriptorDict(
                {
                    "name": agent.name,
                    "description": agent.description,
                    "capabilities": getattr(agent, "capabilities", []),
                    "supported_task_types": getattr(agent, "supported_task_types", []),
                    "priority": getattr(agent, "priority", 0),
                }
            )
            entries.append(payload)
        return entries
