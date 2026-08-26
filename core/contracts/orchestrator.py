from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from core.contracts.response import AgentResponse


@dataclass
class DelegationRequest:
    target_agent: str
    request: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    delegation_id: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    input: Any = None

    def __post_init__(self) -> None:
        if self.depends_on is None:
            self.depends_on = []


@dataclass
class DelegationResult:
    target_agent: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    delegation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DelegationPlan:
    delegations: list[DelegationRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.delegations is None:
            self.delegations = []


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

    @property
    def capabilities(self) -> list[str]:
        ...

    @property
    def supported_task_types(self) -> list[str]:
        ...

    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        ...
