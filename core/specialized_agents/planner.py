from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from core.contracts.execution import Task
from core.contracts.orchestrator import DelegationPlan, DelegationRequest


class DelegationPlanner:
    """Deterministic planning layer for controlled multi-agent delegation."""

    def __init__(self, specialized_agent_registry=None):
        self.specialized_agent_registry = specialized_agent_registry

    def _coerce_delegation_request(self, item: Any, index: int) -> DelegationRequest:
        if isinstance(item, DelegationRequest):
            return item
        if not isinstance(item, dict):
            raise ValueError(f"Delegation {index} must be a request mapping or DelegationRequest.")

        target_agent = item.get("target_agent") or item.get("agent")
        if target_agent is None:
            raise ValueError(f"Delegation {index} must include an explicit target agent.")

        request = item.get("request")
        if request is None:
            request = item.get("query")
        if request is None:
            request = item.get("input")
        if request is None:
            request = {k: v for k, v in item.items() if k not in {"id", "delegation_id", "target_agent", "agent", "depends_on", "metadata", "input"}}

        depends_on = item.get("depends_on") or []
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            raise ValueError(f"Delegation '{target_agent}' has malformed depends_on; expected a list of ids.")

        delegation_id = item.get("delegation_id") or item.get("id")
        if delegation_id is None:
            delegation_id = f"delegation_{index + 1}"

        return DelegationRequest(
            target_agent=str(target_agent),
            request=request,
            metadata=item.get("metadata", {}) or {},
            delegation_id=str(delegation_id),
            depends_on=[str(dep) for dep in depends_on],
            input=item.get("input"),
        )

    def build_plan(self, request: Any) -> DelegationPlan:
        if isinstance(request, DelegationPlan):
            return request

        if isinstance(request, list):
            delegations = [self._coerce_delegation_request(item, idx) for idx, item in enumerate(request)]
            return DelegationPlan(delegations=delegations)

        if not isinstance(request, dict):
            raise ValueError("Delegation plan must be a dict or a list of delegation requests.")

        delegations = request.get("delegations")
        if delegations is None:
            raise ValueError("Delegation plan requires a 'delegations' list.")
        if not isinstance(delegations, list):
            raise ValueError("Delegations must be provided as a list.")

        normalized = [self._coerce_delegation_request(item, idx) for idx, item in enumerate(delegations)]
        return DelegationPlan(delegations=normalized)

    def validate(self, plan: DelegationPlan) -> None:
        if not isinstance(plan, DelegationPlan):
            raise ValueError("A valid DelegationPlan is required.")

        if not plan.delegations:
            raise ValueError("Delegation plan must contain at least one delegation.")

        ids: set[str] = set()
        id_map: Dict[str, DelegationRequest] = {}
        for delegation in plan.delegations:
            if not isinstance(delegation, DelegationRequest):
                raise ValueError("Each plan item must be a DelegationRequest.")

            delegation_id = delegation.delegation_id or delegation.target_agent
            if not delegation_id:
                raise ValueError("Each delegation requires a non-empty delegation id.")
            if delegation_id in ids:
                raise ValueError(f"Duplicate delegation id: {delegation_id}")
            ids.add(delegation_id)
            id_map[delegation_id] = delegation

            if delegation.target_agent in {"general", "main", "agent"}:
                if delegation.request is None:
                    raise ValueError(f"Delegation '{delegation_id}' must include a request for the general agent.")
                continue

            if self.specialized_agent_registry is not None:
                try:
                    self.specialized_agent_registry.get(delegation.target_agent)
                except KeyError as exc:
                    raise ValueError(f"Delegation '{delegation_id}' references unknown agent: {delegation.target_agent}") from exc

            for dependency in delegation.depends_on:
                if dependency == delegation_id:
                    raise ValueError(f"Delegation '{delegation_id}' has a self-dependency.")
                if dependency not in id_map and dependency not in ids:
                    # allow the dependency to be validated against the full plan below
                    pass
                if dependency not in ids:
                    raise ValueError(f"Delegation '{delegation_id}' depends on unknown delegation id: {dependency}")

        for delegation in plan.delegations:
            for dependency in delegation.depends_on:
                if dependency == delegation.delegation_id or delegation.delegation_id is None:
                    continue
                if dependency not in ids:
                    raise ValueError(f"Delegation '{delegation.delegation_id}' depends on unknown delegation id: {dependency}")

        for delegation in plan.delegations:
            if delegation.request is not None and isinstance(delegation.request, dict):
                refs = set()
                self._collect_from_task_inputs(delegation.request, refs)
                for ref in refs:
                    if ref not in ids:
                        raise ValueError(
                            f"Delegation '{delegation.delegation_id}' references unknown upstream output '{ref}'."
                        )
                    if ref not in (delegation.depends_on or []):
                        raise ValueError(
                            f"Delegation '{delegation.delegation_id}' references upstream output '{ref}' without declaring it in depends_on."
                        )

        # detect cycles with Kahn's algorithm across delegation dependencies
        indegree = {delegation.delegation_id: 0 for delegation in plan.delegations}
        adj = {delegation.delegation_id: [] for delegation in plan.delegations}
        for delegation in plan.delegations:
            for dep in delegation.depends_on:
                adj[dep].append(delegation.delegation_id)
                indegree[delegation.delegation_id] += 1

        ready = [node for node, degree in indegree.items() if degree == 0]
        seen = 0
        while ready:
            current = ready.pop(0)
            seen += 1
            for neighbor in adj.get(current, []):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    ready.append(neighbor)

        if seen != len(plan.delegations):
            raise ValueError("Delegation plan contains a dependency cycle.")

    @staticmethod
    def _collect_from_task_inputs(obj: Any, refs: set[str]) -> None:
        if isinstance(obj, dict):
            if "from_task" in obj:
                value = obj.get("from_task")
                if isinstance(value, str) and value:
                    refs.add(value)
            for value in obj.values():
                DelegationPlanner._collect_from_task_inputs(value, refs)
        elif isinstance(obj, list):
            for item in obj:
                DelegationPlanner._collect_from_task_inputs(item, refs)

    def to_task_plan(self, plan: DelegationPlan) -> List[Task]:
        tasks: List[Task] = []
        for delegation in plan.delegations:
            request_payload = delegation.request
            if request_payload is None:
                request_payload = delegation.input if delegation.input is not None else {}
            if isinstance(request_payload, dict):
                task_input = dict(request_payload)
            else:
                task_input = {"query": str(request_payload)} if request_payload is not None else {}

            if delegation.input is not None and isinstance(task_input, dict):
                task_input.setdefault("input", delegation.input)

            tasks.append(
                Task(
                    id=str(delegation.delegation_id),
                    description=f"Delegate to {delegation.target_agent}",
                    input={
                        "agent": delegation.target_agent,
                        "query": request_payload if not isinstance(request_payload, dict) else request_payload.get("query", request_payload),
                        "delegation": {
                            "id": delegation.delegation_id,
                            "target_agent": delegation.target_agent,
                            "depends_on": list(delegation.depends_on),
                            "metadata": dict(delegation.metadata or {}),
                            "input": delegation.input,
                        },
                        **({"request": request_payload} if request_payload is not None else {}),
                    },
                    metadata={
                        "capability": "workflow",
                        "agent": delegation.target_agent,
                        "delegation_id": delegation.delegation_id,
                        "delegation": True,
                    },
                    depends_on=list(delegation.depends_on),
                )
            )
        return tasks
