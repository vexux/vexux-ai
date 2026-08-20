"""Deterministic system-level evaluation for the Vexux-AI agent."""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi.testclient import TestClient

from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from api.main import app, get_agent
from core.context.context_manager import ContextManager
from core.contracts.response import AgentResponse
from core.tools.calculator import CalculatorTool
from core.tools.registry import ToolRegistry


@dataclass
class EvaluationCase:
    name: str
    category: str
    check: Callable[[], None]


@dataclass
class EvaluationResult:
    name: str
    category: str
    passed: bool
    error: str | None = None


@dataclass
class EvaluationReport:
    results: list[EvaluationResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def category_results(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for result in self.results:
            bucket = summary.setdefault(result.category, {"total": 0, "passed": 0, "failed": 0})
            bucket["total"] += 1
            bucket["passed"] += int(result.passed)
            bucket["failed"] += int(not result.passed)
        return summary

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "categories": self.category_results(),
            "failures": [
                {"name": item.name, "category": item.category, "error": item.error}
                for item in self.results
                if not item.passed
            ],
        }


class EvaluationGateway:
    """Deterministic gateway that returns plans and model responses for a case."""

    def __init__(self, plans: dict[str, dict[str, Any]], model_outputs: dict[str, str] | None = None):
        self.plans = plans
        self.model_outputs = model_outputs or {}
        self.prompts: list[str] = []
        self.replan_mode: str | None = None

    def generate(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)

        if (
            "planning component for an AI agent" in prompt
            or "top-level object MUST have this shape" in prompt
        ):
            for query, structured_plan in self.plans.items():
                if f"User request:\n{query}" in prompt:
                    return json.dumps(structured_plan)
            raise AssertionError("No deterministic plan registered for prompt")

        if "You are replanning an agent task" in prompt:
            if self.replan_mode == "recover_to_model":
                task_id = prompt.split("Failed task ID:\n", 1)[1].splitlines()[0]
                return json.dumps({
                    "tasks": [{
                        "id": task_id,
                        "description": "Recovery response",
                        "capability": "model",
                        "input": {"query": "recovery"},
                    }]
                })
            if self.replan_mode == "repeat_failure":
                task_id = prompt.split("Failed task ID:\n", 1)[1].splitlines()[0]
                return json.dumps({
                    "tasks": [{
                        "id": task_id,
                        "description": "Repeat failing retrieval",
                        "capability": "retrieval",
                        "input": {"query": "failing retrieval"},
                    }]
                })

        if "You are producing the final response" in prompt:
            return "Synthesized multi-task response"

        for query, output in self.model_outputs.items():
            if prompt == query or query in prompt:
                return output

        return "Deterministic model response"


class EvaluationRetrieval:
    def __init__(self, documents: dict[str, list[dict[str, Any]]] | None = None, failures: set[str] | None = None):
        self.documents = documents or {}
        self.failures = failures or set()
        self.calls: list[str] = []

    def retrieve(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        self.calls.append(query)
        if query in self.failures:
            raise RuntimeError("retrieval backend unavailable")
        return self.documents.get(query, [])[:k]


def structured_task(task_id: str, description: str, capability: str, task_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task_id,
        "description": description,
        "capability": capability,
        "input": task_input,
    }


def build_agent(
    plans: dict[str, dict[str, Any]],
    retrieval: EvaluationRetrieval | None = None,
    model_outputs: dict[str, str] | None = None,
    context_manager: ContextManager | None = None,
) -> tuple[Agent, EvaluationGateway, EvaluationRetrieval]:
    gateway = EvaluationGateway(plans, model_outputs)
    retrieval = retrieval or EvaluationRetrieval()
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    context_manager = context_manager or ContextManager()
    agent = Agent(
        execution_manager=ExecutionManager(
            retrieval=retrieval,
            tool_registry=registry,
            model_gateway=gateway,
        ),
        planner=Planner(gateway, registry),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=context_manager,
        response_synthesizer=ResponseSynthesizer(gateway),
    )
    return agent, gateway, retrieval


def run_agent_case(
    query: str,
    plan: dict[str, Any],
    assertion: Callable[[AgentResponse, EvaluationGateway, EvaluationRetrieval], None],
    *,
    retrieval: EvaluationRetrieval | None = None,
    model_outputs: dict[str, str] | None = None,
    session_id: str | None = None,
    context_manager: ContextManager | None = None,
    replan_mode: str | None = None,
) -> None:
    agent, gateway, retrieval = build_agent(
        {query: plan},
        retrieval=retrieval,
        model_outputs=model_outputs,
        context_manager=context_manager,
    )
    gateway.replan_mode = replan_mode
    response = agent.run(query, session_id=session_id)
    assertion(response, gateway, retrieval)


def successful(response: AgentResponse) -> None:
    assert response.success is True, response.error


def assert_general(response: AgentResponse, gateway: EvaluationGateway, retrieval: EvaluationRetrieval) -> None:
    successful(response)
    assert response.trace[0].task_id == "task-1"
    assert response.trace[0].success is True


def assert_retrieval(response: AgentResponse, gateway: EvaluationGateway, retrieval: EvaluationRetrieval) -> None:
    successful(response)
    assert response.trace[0].success is True
    assert response.trace[0].output["context_found"] is True
    assert response.trace[0].output["results"]


def assert_calculator(response: AgentResponse, gateway: EvaluationGateway, retrieval: EvaluationRetrieval) -> None:
    successful(response)
    assert response.trace[0].output == 168


def assert_multi_task(response: AgentResponse, gateway: EvaluationGateway, retrieval: EvaluationRetrieval) -> None:
    successful(response)
    assert [item.task_id for item in response.trace] == ["task-1", "task-2"]
    assert all(item.success for item in response.trace)


def assert_replanning_stops(response: AgentResponse, gateway: EvaluationGateway, retrieval: EvaluationRetrieval) -> None:
    assert response.success is False
    assert len(response.trace) == 3
    assert all(item.success is False for item in response.trace)


def make_cases() -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []

    general_queries = ["Hello", "Explain your role", "Give a concise greeting", "What can you do?", "Tell me a short joke", "Good morning", "Summarize this request", "Respond politely"]
    for index, query in enumerate(general_queries, 1):
        plan = {"tasks": [structured_task("task-1", "General response", "model", {"query": query})]}
        cases.append(EvaluationCase(f"general-{index:02d}", "general", lambda q=query, p=plan: run_agent_case(q, p, assert_general, model_outputs={q: "general answer"})))

    retrieval_queries = ["EC2", "Python", "AWS Lambda", "Java", "S3", "Qwen", "FAISS"]
    for index, query in enumerate(retrieval_queries, 1):
        plan = {"tasks": [structured_task("task-1", "Retrieve context", "retrieval", {"query": query})]}
        retrieval = EvaluationRetrieval({query: [{"score": 0.9, "document": f"Context about {query}"}]})
        cases.append(EvaluationCase(f"retrieval-{index:02d}", "retrieval", lambda q=query, p=plan, r=retrieval: run_agent_case(q, p, assert_retrieval, retrieval=r)))

    for index, expression in enumerate(["24 * 7", "2 + 2", "100 / 4", "5 * 5", "10 - 3", "8 + 9"], 1):
        query = f"Calculate {expression}"
        plan = {"tasks": [structured_task("task-1", "Calculate", "tool", {"tool": "calculator", "arguments": {"expression": expression}})]}
        expected = eval(expression, {"__builtins__": {}}, {})
        def check(response, gateway, retrieval, value=expected):
            successful(response)
            assert response.trace[0].output == value
        cases.append(EvaluationCase(f"calculator-{index:02d}", "calculator", lambda q=query, p=plan, c=check: run_agent_case(q, p, c)))

    multi_queries = ["EC2 and calculate 24 * 7", "Python and calculate 2 + 2", "AWS Lambda and calculate 10 - 3", "Java and calculate 5 * 5", "S3 and calculate 100 / 4"]
    for index, query in enumerate(multi_queries, 1):
        retrieval_query, expression = query.split(" and calculate ")
        plan = {"tasks": [
            structured_task("task-1", "Retrieve context", "retrieval", {"query": retrieval_query}),
            structured_task("task-2", "Calculate", "tool", {"tool": "calculator", "arguments": {"expression": expression}}),
        ]}
        retrieval = EvaluationRetrieval({retrieval_query: [{"score": 0.9, "document": retrieval_query}]})
        cases.append(EvaluationCase(f"multi-retrieval-tool-{index:02d}", "multi-task", lambda q=query, p=plan, r=retrieval: run_agent_case(q, p, assert_multi_task, retrieval=r)))

    for index, expressions in enumerate([("2 + 2", "3 + 3"), ("4 * 4", "5 * 5"), ("10 - 1", "8 / 2")], 1):
        query = f"Calculate {expressions[0]} and calculate {expressions[1]}"
        plan = {"tasks": [
            structured_task("task-1", "Calculate first", "tool", {"tool": "calculator", "arguments": {"expression": expressions[0]}}),
            structured_task("task-2", "Calculate second", "tool", {"tool": "calculator", "arguments": {"expression": expressions[1]}}),
        ]}
        cases.append(EvaluationCase(f"multi-tools-{index:02d}", "multi-tool", lambda q=query, p=plan: run_agent_case(q, p, assert_multi_task)))

    invalid_queries = ["Calculate abc", "Calculate 1 / 0", "Calculate invalid expression", "Use unknown tool"]
    for index, query in enumerate(invalid_queries, 1):
        expression = query.removeprefix("Calculate ")
        plan = {"tasks": [structured_task("task-1", "Invalid calculation", "tool", {"tool": "calculator", "arguments": {"expression": expression}})]}
        def check(response, gateway, retrieval):
            assert response.success is False
            assert response.trace[0].success is False
            assert response.trace[0].error
        cases.append(EvaluationCase(f"invalid-tool-{index:02d}", "invalid-tool", lambda q=query, p=plan, c=check: run_agent_case(q, p, c)))

    for index in range(3):
        query = f"failing retrieval {index}"
        plan = {"tasks": [structured_task("task-1", "Fail retrieval", "retrieval", {"query": query})]}
        retrieval = EvaluationRetrieval(failures={query})
        cases.append(EvaluationCase(f"failure-replan-{index + 1:02d}", "failure-replanning", lambda q=query, p=plan, r=retrieval: run_agent_case(q, p, assert_replanning_stops, retrieval=r, replan_mode="repeat_failure")))

    context_manager = ContextManager()
    first_query = "What is EC2?"
    second_query = "What about its pricing?"
    session_plan = {"tasks": [structured_task("task-1", "Answer", "model", {"query": first_query})]}
    followup_plan = {"tasks": [structured_task("task-1", "Answer follow-up", "model", {"query": second_query})]}
    def session_case():
        agent, gateway, _ = build_agent({first_query: session_plan, second_query: followup_plan}, model_outputs={first_query: "EC2 context", second_query: "Pricing context"}, context_manager=context_manager)
        assert agent.run(first_query, session_id="session-a").success
        result = agent.run(second_query, session_id="session-a")
        assert result.success
        followup_prompt = next(
            prompt for prompt in gateway.prompts
            if f"User request:\n{second_query}" in prompt
        )
        assert first_query in followup_prompt
    cases.append(EvaluationCase("session-follow-up", "session", session_case))

    def isolation_case():
        agent, gateway, _ = build_agent({first_query: session_plan, second_query: followup_plan}, model_outputs={first_query: "EC2 context", second_query: "Pricing context"}, context_manager=ContextManager())
        agent.run(first_query, session_id="session-a")
        agent.run(second_query, session_id="session-b")
        followup_prompt = next(
            prompt for prompt in gateway.prompts
            if f"User request:\n{second_query}" in prompt
        )
        assert first_query not in followup_prompt
    cases.append(EvaluationCase("session-isolation", "session", isolation_case))

    api_cases = [
        ("api-general", {"query": "Hello"}),
        ("api-retrieval", {"query": "What is EC2?"}),
        ("api-tool", {"query": "Calculate 24 * 7"}),
        ("api-session", {"query": "Follow up", "session_id": "session-a"}),
        ("api-user", {"query": "Hello", "user_id": "user-a"}),
        ("api-multi-task", {"query": "What is EC2 and calculate 24 * 7"}),
    ]
    for name, payload in api_cases:
        def api_case(body=payload):
            fake_response = AgentResponse(success=True, output="ok", trace=[], metadata={"request_id": "evaluation-request", "session_id": body.get("session_id"), "user_id": body.get("user_id")})
            class FakeAgent:
                def run(self, query, session_id=None, user_id=None):
                    return fake_response
            app.dependency_overrides[get_agent] = lambda: FakeAgent()
            try:
                response = TestClient(app).post("/api/v1/agent/run", json=body)
                assert response.status_code == 200
                data = response.json()
                assert data["request_id"] == "evaluation-request"
                assert data["success"] is True
            finally:
                app.dependency_overrides.clear()
        cases.append(EvaluationCase(name, "api", api_case))

    return cases


def run_evaluation() -> EvaluationReport:
    report = EvaluationReport()
    for case in make_cases():
        try:
            case.check()
            report.results.append(EvaluationResult(case.name, case.category, True))
        except Exception as exc:
            report.results.append(EvaluationResult(case.name, case.category, False, f"{type(exc).__name__}: {exc}"))
    return report


def main() -> int:
    report = run_evaluation()
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
