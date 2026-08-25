from typing import Any, Protocol

from core.contracts.response import AgentResponse


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
