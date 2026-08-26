from __future__ import annotations

from typing import Any

from core.contracts.orchestrator import DelegationPlan, DelegationRequest, DelegationResult
from core.contracts.response import AgentResponse
from core.specialized_agents.planner import DelegationPlanner
from core.specialized_agents.selector import AgentSelectionRequest, AgentSelector


class Orchestrator:
    """Minimal orchestration boundary.

    It chooses the execution owner and delegates to the existing Agent or a
    registered specialized agent. It never executes tools, retrievals, or DAG
    tasks directly.
    """

    def __init__(self, agent, workflow_registry=None, specialized_agent_registry=None, agent_selector=None, delegation_planner=None):
        self.agent = agent
        self.workflow_registry = workflow_registry
        self.specialized_agent_registry = specialized_agent_registry
        self.agent_selector = agent_selector or AgentSelector()
        self.delegation_planner = delegation_planner or DelegationPlanner(specialized_agent_registry)

    def _delegate_one(self, delegation: DelegationRequest, session_id=None, user_id=None):
        target = delegation.target_agent
        request = delegation.request

        if target in {"general", "main", "agent"}:
            query = request.get("query") if isinstance(request, dict) else request
            response = self.agent.run(query, session_id=session_id, user_id=user_id)
        else:
            if self.specialized_agent_registry is None:
                return DelegationResult(
                    target_agent=target,
                    success=False,
                    error=f"Specialized agent '{target}' is unavailable.",
                    delegation_id=delegation.delegation_id,
                    metadata={"selected_mode": "delegated", "selected_agent": target},
                )
            try:
                specialized_agent = self.specialized_agent_registry.get(target)
            except KeyError:
                return DelegationResult(
                    target_agent=target,
                    success=False,
                    error=f"Unknown specialized agent: {target}",
                    delegation_id=delegation.delegation_id,
                    metadata={"selected_mode": "delegated", "selected_agent": target},
                )
            response = specialized_agent.run(request, session_id=session_id, user_id=user_id)

        metadata = dict(response.metadata or {})
        metadata.setdefault("selected_mode", "delegated")
        metadata["selected_agent"] = target
        if delegation.delegation_id is not None:
            metadata["delegation_id"] = delegation.delegation_id

        return DelegationResult(
            target_agent=target,
            success=response.success,
            output=response.output,
            error=response.error,
            delegation_id=delegation.delegation_id,
            metadata=metadata,
        )

    def _parse_delegations(self, request: dict):
        delegations = request.get("delegations")
        if delegations is None:
            return []
        if not isinstance(delegations, list):
            raise ValueError("Delegations must be a list of delegation requests.")

        parsed = []
        for item in delegations:
            if isinstance(item, DelegationRequest):
                parsed.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError("Each delegation entry must be a request mapping.")

            target_agent = item.get("target_agent") or item.get("agent")
            if target_agent is None:
                raise ValueError("Each delegation must include an explicit target agent.")

            payload = item.get("request")
            if payload is None:
                payload = item.get("query")
            if payload is None:
                payload = item.get("input")
            if payload is None:
                payload = {k: v for k, v in item.items() if k not in {"target_agent", "agent", "delegation_id", "id", "metadata", "depends_on", "input"}}

            parsed.append(
                DelegationRequest(
                    target_agent=str(target_agent),
                    request=payload,
                    metadata=item.get("metadata", {}) or {},
                    delegation_id=item.get("delegation_id") or item.get("id"),
                    depends_on=[str(dep) for dep in (item.get("depends_on") or [])],
                    input=item.get("input"),
                )
            )
        return parsed

    def _build_delegation_plan(self, request: dict) -> DelegationPlan:
        planner = self.delegation_planner
        plan = planner.build_plan(request)
        planner.validate(plan)
        return plan

    def _execute_delegation_plan(self, plan: DelegationPlan, session_id=None, user_id=None):
        remaining = {delegation.delegation_id: delegation for delegation in plan.delegations}
        ordered = []
        while remaining:
            ready = [
                delegation for delegation in plan.delegations
                if delegation.delegation_id in remaining and all(dep not in remaining for dep in delegation.depends_on)
            ]
            if not ready:
                break
            for delegation in ready:
                ordered.append(self._delegate_one(delegation, session_id=session_id, user_id=user_id))
                remaining.pop(delegation.delegation_id, None)
        if remaining:
            for delegation in plan.delegations:
                if delegation.delegation_id in remaining:
                    ordered.append(
                        DelegationResult(
                            target_agent=delegation.target_agent,
                            success=False,
                            output=None,
                            error=f"Delegation '{delegation.delegation_id}' is blocked by unresolved dependencies.",
                            delegation_id=delegation.delegation_id,
                            metadata={"selected_mode": "delegated", "selected_agent": delegation.target_agent, "dependency_status": "blocked"},
                        )
                    )
        return ordered

    def _resolve_metadata_agent(self, request: dict):
        if self.specialized_agent_registry is None:
            return None, None

        metadata = request.get("metadata") or {}
        if isinstance(metadata, dict):
            explicit = metadata.get("agent") or metadata.get("selected_agent")
        else:
            explicit = None

        query = request.get("query")
        if query is None:
            query = request.get("task") or request.get("question") or request.get("request")

        selection = self.agent_selector.select(
            AgentSelectionRequest(
                query=str(query) if query is not None else "",
                explicit_agent=request.get("agent") or explicit,
                metadata=metadata,
            ),
            self.specialized_agent_registry,
        )
        if selection.selected_agent is None:
            return None, selection
        return selection.selected_agent, selection

    def run(
        self,
        request: Any,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AgentResponse:
        if isinstance(request, dict):
            delegations = request.get("delegations")
            if delegations is not None:
                try:
                    plan = self._build_delegation_plan(request)
                    results = self._execute_delegation_plan(plan, session_id=session_id, user_id=user_id)
                except ValueError as exc:
                    return AgentResponse(
                        success=False,
                        error=str(exc),
                        trace=[],
                        metadata={"selected_mode": "delegated"},
                    )

                success = all(item.success for item in results)
                return AgentResponse(
                    success=success,
                    output=results,
                    error=None if success else "One or more delegated agent requests failed.",
                    trace=[],
                    metadata={
                        "selected_mode": "delegated",
                        "delegation_count": len(results),
                        "successful_delegations": sum(1 for item in results if item.success),
                        "failed_delegations": sum(1 for item in results if not item.success),
                    },
                )

            selected_agent = request.get("agent")
            workflow_name = request.get("workflow")
            workflow_input = {
                k: v for k, v in request.items() if k not in {"agent", "workflow", "query", "session_id", "user_id"}
            }
            query = request.get("query")

            if selected_agent is not None:
                if selected_agent in {"general", "main", "agent"}:
                    if query is None:
                        return AgentResponse(
                            success=False,
                            error="Request must include a query for the general agent.",
                            trace=[],
                            metadata={"selected_mode": "agent", "selected_agent": selected_agent},
                        )
                    return self.agent.run(query, session_id=session_id, user_id=user_id)
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

            if self.specialized_agent_registry is not None and query is not None:
                resolved_agent, selection = self._resolve_metadata_agent(request)
                if resolved_agent is not None:
                    try:
                        specialized_agent = self.specialized_agent_registry.get(resolved_agent)
                    except KeyError:
                        return AgentResponse(
                            success=False,
                            error=f"Unknown specialized agent: {resolved_agent}",
                            trace=[],
                            metadata={"selected_mode": "specialized_agent", "selected_agent": resolved_agent},
                        )
                    result = specialized_agent.run(request, session_id=session_id, user_id=user_id)
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata.setdefault("selected_mode", "specialized_agent")
                    result.metadata["selected_agent"] = resolved_agent
                    result.metadata["selection_reason"] = selection.reason if selection is not None else "capability_match"
                    return result

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
