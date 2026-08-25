from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from core.contracts.response import AgentResponse


@dataclass
class DelegationRequest:
    target_agent: str
    request: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    delegation_id: Optional[str] = None


@dataclass
class DelegationResult:
    target_agent: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    delegation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class OrchestratorContract(Protocol):
    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        ...


class SpecializedAgentContract(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        ...
