from dataclasses import dataclass

from core.contracts.response import AgentResponse
from evaluation.benchmark import (
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
