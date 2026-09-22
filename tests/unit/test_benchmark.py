from dataclasses import dataclass

from core.contracts.response import AgentResponse
from core.contracts.observation import Observation
from evaluation.benchmark import (
    BenchmarkConfig,
    BenchmarkScenario,
    default_scenarios,
    run_benchmark,
)


@dataclass
class FakeAgent:
    calls: list[tuple[str, str | None]]

    def run(self, query, user_id=None):
        self.calls.append((query, user_id))
        if user_id == "support_user":
            return AgentResponse(
                success=False,
                error="Authorization denied for fraud_graph.",
                trace=[],
                metadata={"authorization_check": True, "user_id": user_id},
            )
        return AgentResponse(
            success=True,
            output={"ok": True},
            trace=[],
            metadata={},
        )


def test_default_benchmark_scenarios_are_stable_and_complete():
    scenarios = default_scenarios()
    assert len(scenarios) >= 11
    assert {"general-conversation", "knowledge-rag", "tool-use", "fraud-investigation"} <= {
        scenario.scenario_id for scenario in scenarios
    }


def test_benchmark_normalizes_authorization_and_invalid_actor_results(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    agent = FakeAgent([])
    scenarios = [
        BenchmarkScenario("allowed", "fraud_graph", "authorized", "investigator", "fraud_graph", "allowed"),
        BenchmarkScenario("denied", "fraud_graph", "denied", "support_user", "fraud_graph", "denied"),
        BenchmarkScenario("invalid", "fraud_graph", "rejected", "admin", "fraud_graph", "rejected"),
    ]
    report = run_benchmark(lambda: agent, scenarios)
    assert all(metric.success for metric in report.metrics)
    assert [metric.authorization_result for metric in report.metrics] == ["allowed", "denied", "rejected"]
    assert len(agent.calls) == 2


def test_benchmark_records_provider_model_workflow_and_execution_outcome():
    class WorkflowAgent:
        def run(self, query, user_id=None):
            return AgentResponse(
                success=True,
                output={"ok": True},
                trace=[Observation(
                    success=True,
                    metadata={"capability": "workflow", "workflow": "fraud_investigation"},
                )],
                metadata={},
            )

    report = run_benchmark(
        WorkflowAgent,
        [BenchmarkScenario("workflow", "Investigate C1001", "workflow")],
        benchmark_config=BenchmarkConfig("ollama", "phi3:latest", 2),
    )
    assert len(report.metrics) == 2
    assert all(metric.provider == "ollama" for metric in report.metrics)
    assert all(metric.model == "phi3:latest" for metric in report.metrics)
    assert all(metric.selected_workflow == "fraud_investigation" for metric in report.metrics)
    assert all(metric.execution_success for metric in report.metrics)


def test_benchmark_marks_intermittent_failures():
    class FlakyAgent:
        calls = 0

        def run(self, query, user_id=None):
            self.calls += 1
            return AgentResponse(
                success=self.calls == 1,
                error=None if self.calls == 1 else "planner failed",
                trace=[],
                metadata={},
            )

    flaky = FlakyAgent()
    report = run_benchmark(
        lambda: flaky,
        [BenchmarkScenario("flaky", "hey", "general")],
        benchmark_config=BenchmarkConfig("ollama", "qwen3:4b", 2),
    )
    assert [metric.failure_repeatability for metric in report.metrics] == [None, "intermittent"]


def test_benchmark_comparison_summary_is_human_readable():
    class SuccessfulAgent:
        def run(self, query, user_id=None):
            return AgentResponse(success=True, trace=[], metadata={})

    report = run_benchmark(
        SuccessfulAgent,
        [BenchmarkScenario("one", "hey", "general")],
        benchmark_config=BenchmarkConfig("ollama", "phi3:latest"),
    )
    from evaluation.benchmark import BenchmarkComparison

    summary = BenchmarkComparison([report]).summary()
    assert "provider/model" in summary
    assert "ollama/phi3:latest" in summary
