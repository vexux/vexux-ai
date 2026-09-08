"""Bounded, evidence-driven fraud investigation workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.observer import Observer
from core.audit_logger import emit
from core.contracts.audit import make_event
from core.contracts.evidence import Evidence, EvidenceSet
from core.contracts.execution import AgentContext, ExecutionResult, Task

from apps.fraud.domain import InvestigationResult


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class InvestigationStep:
    id: str
    action: str
    resource: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 1
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    output: Any = None
    error: str | None = None
    evidence: EvidenceSet = field(default_factory=EvidenceSet)

    def as_task(self) -> Task:
        capability = "retrieval" if self.action == "retrieve" else "tool"
        return Task(
            id=self.id,
            description=self.expected_output or self.action,
            input=self.input,
            metadata={"capability": capability, "resource": self.resource},
            depends_on=list(self.depends_on),
        )


@dataclass
class InvestigationPlan:
    goal: str
    subject_id: str
    steps: list[InvestigationStep]
    max_steps: int = 10
    max_replans: int = 2

    def validate(self) -> None:
        if not self.goal.strip() or not self.subject_id.strip():
            raise ValueError("Investigation plan requires a goal and subject_id.")
        if len(self.steps) > self.max_steps:
            raise ValueError("Investigation plan exceeds maximum step limit.")
        ids = {step.id for step in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Investigation plan contains duplicate step ids.")
        for step in self.steps:
            if step.max_retries < 0 or any(dep not in ids for dep in step.depends_on):
                raise ValueError(f"Invalid dependencies for step '{step.id}'.")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {step.id: step for step in self.steps}

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("Investigation plan contains a dependency cycle.")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step in by_id:
            visit(step)


class FraudInvestigationPlanner:
    """Deterministic planner for the bounded fraud investigation DAG."""

    def __init__(self, max_steps: int = 10, max_replans: int = 2, max_retries_per_step: int = 1):
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.max_retries_per_step = max_retries_per_step

    def create_plan(self, customer_id: str, goal: str | None = None) -> InvestigationPlan:
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValueError("customer_id must be a non-empty string.")
        customer_id = customer_id.strip()
        plan = InvestigationPlan(
            goal=goal or f"Investigate {customer_id} for suspicious activity.",
            subject_id=customer_id,
            max_steps=self.max_steps,
            max_replans=self.max_replans,
            steps=[
                InvestigationStep(
                    "resolve_subject", "retrieve", "customer_graph",
                    {"query": f"Resolve customer {customer_id}", "source": "customer_graph",
                     "operation": "get_node", "params": {"node_id": customer_id}},
                    "customer subject", max_retries=self.max_retries_per_step,
                ),
                InvestigationStep(
                    "customer_context", "retrieve", "customer_graph",
                    {"query": f"Retrieve customer graph context for {customer_id}", "source": "customer_graph",
                     "operation": "get_neighbors", "params": {"node_id": customer_id, "direction": "both"}},
                    "customer relationships", ["resolve_subject"], self.max_retries_per_step,
                ),
                InvestigationStep(
                    "transactions", "retrieve", "business_db",
                    {"query": "SELECT transaction_id, account_id, customer_id, merchant_id, amount, status "
                              "FROM transactions WHERE customer_id = %s ORDER BY occurred_at",
                     "source": "business_db", "parameters": (customer_id,)},
                    "transactions", ["resolve_subject"], self.max_retries_per_step,
                ),
                InvestigationStep(
                    "alerts", "retrieve", "business_db",
                    {"query": "SELECT alert_id, customer_id, transaction_id, alert_type, severity, status "
                              "FROM fraud_alerts WHERE customer_id = %s ORDER BY created_at",
                     "source": "business_db", "parameters": (customer_id,)},
                    "fraud alerts", ["resolve_subject"], self.max_retries_per_step,
                ),
                InvestigationStep(
                    "investigations", "retrieve", "business_db",
                    {"query": "SELECT investigation_id, customer_id, fraud_case_id, status "
                              "FROM investigations WHERE customer_id = %s ORDER BY opened_at",
                     "source": "business_db", "parameters": (customer_id,)},
                    "investigation records", ["resolve_subject"], self.max_retries_per_step,
                ),
                InvestigationStep(
                    "fraud_context", "retrieve", "fraud_graph",
                    {"query": f"Retrieve fraud graph context for {customer_id}", "source": "fraud_graph",
                     "operation": "get_neighbors", "params": {"node_id": customer_id, "direction": "both"}},
                    "fraud relationships", ["customer_context"], self.max_retries_per_step,
                ),
            ],
        )
        plan.validate()
        return plan


class FraudInvestigationWorkflow:
    """Execute a deterministic fraud plan through the existing execution path."""

    def __init__(
        self,
        investigation_service,
        execution_manager,
        resource_router=None,
        planner=None,
        max_steps: int = 10,
        max_replans: int = 2,
        max_retries_per_step: int = 1,
    ):
        if min(max_steps, max_replans, max_retries_per_step) < 0:
            raise ValueError("Workflow bounds must not be negative.")
        self.service = investigation_service
        self.execution_manager = execution_manager
        self.resource_router = resource_router
        self.planner = planner or FraudInvestigationPlanner(
            max_steps=max_steps,
            max_replans=max_replans,
            max_retries_per_step=max_retries_per_step,
        )
        self.observer = Observer()
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.max_retries_per_step = max_retries_per_step

    def create_plan(self, customer_id: str, goal: str | None = None) -> InvestigationPlan:
        return self.planner.create_plan(customer_id, goal)

    @staticmethod
    def _audit(event_type: str, request_id: str, **kwargs: Any) -> None:
        emit(make_event(event_type=event_type, request_id=request_id, **kwargs))

    @staticmethod
    def _results(output: dict[str, Any] | None) -> list[dict[str, Any]]:
        return list((output or {}).get("results") or [])

    @staticmethod
    def _has_suspicious_relationship(output: dict[str, Any] | None) -> bool:
        for item in (output or {}).get("results", []):
            relationship = item.get("relationship", {})
            if str(relationship.get("type", "")).upper() in {
                "SHARES_DEVICE_WITH", "SHARED_DEVICE", "LINKED_TO",
            }:
                return True
        return False

    def _execute_step(self, step: InvestigationStep, context: AgentContext) -> None:
        step.status = StepStatus.RUNNING
        if self.resource_router is not None and step.resource is not None:
            selected = {item.name for item in self.resource_router.select(step.resource)}
            if step.resource not in selected:
                raise RuntimeError(f"Investigation resource is not registered: {step.resource}")
        task = step.as_task()
        for attempt in range(step.max_retries + 1):
            step.attempts += 1
            result: ExecutionResult = self.execution_manager.execute(task, context)
            observation = self.observer.observe(result, task)
            if observation.success or (
                result.error == "No sufficiently relevant retrieval context found"
                and isinstance(result.output, dict)
                and result.output.get("results") == []
            ):
                step.status = StepStatus.SUCCEEDED
                step.output = result.output or {"results": []}
                step.evidence.add(Evidence(
                    step.resource or "workflow",
                    str(step.output),
                    "workflow_observation",
                    {"step_id": step.id, "attempt": step.attempts},
                ))
                return
            step.error = observation.error or "step execution failed"
            self._audit("step_execution", context.request_id, task_id=step.id, status="failed",
                        resource_name=step.resource, metadata={"attempt": step.attempts, "error": step.error})
            if attempt < step.max_retries:
                self._audit("step_retry", context.request_id, task_id=step.id, status="retrying")
        step.status = StepStatus.FAILED
        raise RuntimeError(f"Investigation step '{step.id}' failed: {step.error}")

    def run(self, customer_id: str, actor: str = "investigator") -> InvestigationResult:
        plan = self.create_plan(customer_id)
        request_id = str(uuid.uuid4())
        context = AgentContext(request_id=request_id, user_id=actor)
        self._audit("investigation_started", request_id, status="started",
                    metadata={"subject_id": customer_id, "goal": plan.goal})
        self._audit("plan_created", request_id, status="created",
                    metadata={"step_count": len(plan.steps), "max_replans": plan.max_replans})
        outputs: dict[str, Any] = {}
        replans = 0
        try:
            index = 0
            while index < len(plan.steps):
                step = plan.steps[index]
                if any(
                    next(item for item in plan.steps if item.id == dependency).status
                    != StepStatus.SUCCEEDED
                    for dependency in step.depends_on
                ):
                    step.status = StepStatus.BLOCKED
                    raise RuntimeError(f"Investigation step '{step.id}' is blocked by a failed dependency.")
                self._audit("step_execution", request_id, task_id=step.id, status="started",
                            resource_name=step.resource)
                self._execute_step(step, context)
                outputs[step.id] = step.output
                self._audit("step_execution", request_id, task_id=step.id, status="completed",
                            resource_name=step.resource)
                if step.id == "fraud_context" and self._has_suspicious_relationship(step.output):
                    if replans >= plan.max_replans:
                        raise RuntimeError("Investigation replan limit exhausted.")
                    replans += 1
                    related = InvestigationStep(
                        "related_entities",
                        "retrieve",
                        "fraud_graph",
                        {"query": f"Inspect related entities for {customer_id}", "source": "fraud_graph",
                         "operation": "get_neighbors", "params": {"node_id": customer_id, "direction": "both"}},
                        "related entities",
                        ["fraud_context"],
                        self.max_retries_per_step,
                    )
                    if len(plan.steps) >= plan.max_steps:
                        raise RuntimeError("Investigation step limit exhausted during replanning.")
                    plan.steps.insert(index + 1, related)
                    plan.validate()
                    self._audit("replan", request_id, status="created",
                                metadata={"replan_count": replans, "reason": "suspicious_relationship"})
                index += 1
            evidence = EvidenceSet()
            for step in plan.steps:
                for item in step.evidence.items:
                    evidence.add(item)
            customer_node = outputs["resolve_subject"]["result"]
            result = self.service.build_result(
                customer_node=customer_node,
                fraud_neighbors=self._results(outputs.get("fraud_context")),
                transaction_rows=self._results(outputs.get("transactions")),
                alert_rows=self._results(outputs.get("alerts")),
                investigation_rows=self._results(outputs.get("investigations")),
                evidence=evidence,
                resources_consulted=[
                    step.resource for step in plan.steps
                    if step.status == StepStatus.SUCCEEDED and step.resource
                ],
            )
            self._audit("investigation_completed", request_id, status="completed",
                        metadata={"risk_assessment": result.risk_assessment})
            return result
        except Exception as exc:
            self._audit("investigation_failed", request_id, status="failed",
                        metadata={"error": str(exc), "replans": replans})
            raise


__all__ = [
    "FraudInvestigationWorkflow",
    "InvestigationPlan",
    "InvestigationStep",
    "StepStatus",
]
