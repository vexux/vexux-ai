from typing import Any

from core.contracts.response import AgentResponse


class ResearchAgent:
    name = "research"
    description = "Adapter for research-oriented requests using the existing Agent execution stack."

    def __init__(self, agent):
        self.agent = agent

    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        if isinstance(request, dict):
            query = request.get("query")
            if query is None:
                return AgentResponse(
                    success=False,
                    error="Research request must include a query.",
                    trace=[],
                    metadata={"selected_mode": "specialized_agent", "selected_agent": self.name},
                )
            result = self.agent.run(query, session_id=session_id, user_id=user_id)
            if result.metadata is None:
                result.metadata = {}
            result.metadata["selected_mode"] = "specialized_agent"
            result.metadata["selected_agent"] = self.name
            return result

        if request is None:
            return AgentResponse(
                success=False,
                error="Research request cannot be empty.",
                trace=[],
                metadata={"selected_mode": "specialized_agent", "selected_agent": self.name},
            )

        result = self.agent.run(str(request), session_id=session_id, user_id=user_id)
        if result.metadata is None:
            result.metadata = {}
        result.metadata["selected_mode"] = "specialized_agent"
        result.metadata["selected_agent"] = self.name
        return result
