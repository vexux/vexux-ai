from __future__ import annotations

from typing import Any

from core.contracts.response import AgentResponse


class Orchestrator:
    """Minimal orchestration boundary.

    It chooses the execution owner and delegates to the existing Agent or a
    registered specialized agent. It never executes tools, retrievals, or DAG
    tasks directly.
    """

    def __init__(self, agent, workflow_registry=None, specialized_agent_registry=None):
        self.agent = agent
        self.workflow_registry = workflow_registry
        self.specialized_agent_registry = specialized_agent_registry

    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        if isinstance(request, dict):
            selected_agent = request.get("agent")
            workflow_name = request.get("workflow")
            workflow_input = {
                k: v for k, v in request.items() if k not in {"agent", "workflow", "query", "session_id", "user_id"}
            }
            query = request.get("query")

            if selected_agent is not None:
                if self.specialized_agent_registry is None:
                    return AgentResponse(
                        success=False,
                        error=f"Specialized agent '{selected_agent}' is unavailable.",
                        trace=[],
                        metadata={"selected_mode": "specialized_agent", "selected_agent": selected_agent},
                    )
                try:
                    specialized_agent = self.specialized_agent_registry.get(selected_agent)
                except KeyError:
                    return AgentResponse(
                        success=False,
                        error=f"Unknown specialized agent: {selected_agent}",
                        trace=[],
                        metadata={"selected_mode": "specialized_agent", "selected_agent": selected_agent},
                    )
                result = specialized_agent.run(request, session_id=session_id, user_id=user_id)
                if result.metadata is None:
                    result.metadata = {}
                result.metadata["selected_mode"] = "specialized_agent"
                result.metadata["selected_agent"] = selected_agent
                return result

            if workflow_name is not None:
                if self.workflow_registry is None:
                    return AgentResponse(
                        success=False,
                        error=f"Workflow '{workflow_name}' is unavailable.",
                        trace=[],
                        metadata={"selected_mode": "workflow", "workflow_name": workflow_name},
                    )
                try:
                    self.workflow_registry.get(workflow_name)
                except KeyError:
                    return AgentResponse(
                        success=False,
                        error=f"Unknown workflow: {workflow_name}",
                        trace=[],
                        metadata={"selected_mode": "workflow", "workflow_name": workflow_name},
                    )
                return self.agent.run_workflow(
                    workflow_name=workflow_name,
                    workflow_input=workflow_input,
                    session_id=session_id,
                    user_id=user_id,
                )
            if query is None:
                return AgentResponse(
                    success=False,
                    error="Request must include a query or an explicit workflow selection.",
                    trace=[],
                    metadata={"selected_mode": "agent"},
                )
            return self.agent.run(
                query,
                session_id=session_id,
                user_id=user_id,
            )

        # direct text request -> agent mode
        if request is None:
            return AgentResponse(
                success=False,
                error="Request cannot be empty.",
                trace=[],
                metadata={"selected_mode": "agent"},
            )

        return self.agent.run(
            str(request),
            session_id=session_id,
            user_id=user_id,
        )
