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
