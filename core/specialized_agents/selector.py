from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class AgentSelectionRequest:
    query: str
    explicit_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSelectionResult:
    selected_agent: Optional[str] = None
    reason: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentSelector:
    """Deterministic metadata-based agent selection.

    Selection priority:
    1. explicit agent selection
    2. metadata/capability matching
    3. default agent
    """

    @staticmethod
    def _normalize(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        tokens: List[str] = []
        for item in value:
            if not item:
                continue
            tokens.extend(re.findall(r"[a-z0-9]+", str(item).lower()))
        return tokens

    @staticmethod
    def _score_agent(agent: Any, query: str) -> tuple[int, int, str]:
        query_lower = query.lower()
        query_tokens = set(re.findall(r"[a-z0-9]+", query_lower))

        capability_tokens: List[str] = []
        for field_name in ("capabilities", "supported_task_types"):
            capability_tokens.extend(AgentSelector._normalize(getattr(agent, field_name, [])))

        description_tokens = AgentSelector._normalize(getattr(agent, "description", ""))
        name_tokens = AgentSelector._normalize(getattr(agent, "name", ""))

        score = 0
        matched = False
        for token in query_tokens:
            if token in capability_tokens or token in name_tokens:
                score += 3
                matched = True
            elif token in description_tokens:
                score += 1
                matched = True

        for capability in getattr(agent, "capabilities", []) or []:
            capability_text = str(capability).lower()
            if capability_text in query_lower:
                score += 4
                matched = True
            elif capability_text.split("_") and any(part in query_lower for part in capability_text.split("_")):
                score += 2
                matched = True

        priority = int(getattr(agent, "priority", 0) or 0)
        if not matched:
            return 0, priority, str(getattr(agent, "name", ""))
        score += priority
        return score, priority, str(getattr(agent, "name", ""))

    def select(self, request: AgentSelectionRequest, registry) -> AgentSelectionResult:
        explicit = request.explicit_agent
        if explicit is not None:
            try:
                registry.get(explicit)
            except KeyError:
                return AgentSelectionResult(
                    selected_agent=None,
                    reason=f"Unknown specialized agent: {explicit}",
                    metadata={"explicit_agent": explicit},
                )
            return AgentSelectionResult(
                selected_agent=explicit,
                reason="explicit",
                metadata={"explicit_agent": explicit},
            )

        candidates = registry.list_agents()
        if not candidates:
            return AgentSelectionResult(selected_agent=None, reason="no_agents_registered", metadata={})

        scored = []
        for name in candidates:
            agent = registry.get(name)
            score, priority, _ = self._score_agent(agent, request.query)
            if score > 0:
                scored.append((score, priority, name))

        if not scored:
            return AgentSelectionResult(selected_agent=None, reason="no_metadata_match", metadata={})

        _, _, selected = sorted(scored, key=lambda item: (-item[0], -item[1], item[2]))[0]
        return AgentSelectionResult(
            selected_agent=selected,
            reason="capability_match",
            metadata={"query": request.query, "matched_agent": selected},
        )
