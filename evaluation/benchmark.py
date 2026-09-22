"""Reusable, provider-neutral runtime benchmark for the fraud agent."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Iterator

from apps.fraud.identity import validate_actor
from core.contracts.response import AgentResponse
from core.config import provider_diagnostic


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    query: str
    expected_behavior: str
    actor: str | None = None
    expected_resource: str | None = None
    expected_authorization: str | None = None


@dataclass(frozen=True)
class BenchmarkConfig:
    """One explicit provider/model configuration for a benchmark run."""

    provider: str = "ollama"
    model: str = "qwen3:4b"
    repetitions: int = 2

    def __post_init__(self) -> None:
        if self.repetitions < 1:
            raise ValueError("Benchmark repetitions must be at least 1.")


@dataclass
class BenchmarkMetric:
    scenario_id: str
    provider: str
    model: str
    repetition: int
    expected_behavior: str
    actual_result: str
    success: bool
    execution_success: bool = False
    capability_or_intent: str | None = None
    selected_resource: str | None = None
    selected_workflow: str | None = None
    structured_output_valid: bool = False
    authorization_result: str | None = None
    latency_ms: float = 0.0
    error_category: str | None = None
    failure_repeatability: str | None = None
    error: str | None = None


@dataclass
class BenchmarkReport:
    provider: dict[str, str]
    metrics: list[BenchmarkMetric]

    @property
    def passed(self) -> int:
        return sum(metric.success for metric in self.metrics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total": len(self.metrics),
            "passed": self.passed,
            "failed": len(self.metrics) - self.passed,
            "metrics": [asdict(metric) for metric in self.metrics],
        }


@dataclass
class BenchmarkComparison:
    reports: list[BenchmarkReport]

    def as_dict(self) -> dict[str, Any]:
        return {"reports": [report.as_dict() for report in self.reports]}

    def summary(self) -> str:
        lines = ["Model baseline summary", "provider/model | passed | total | execution failures | repeatable failures"]
        for report in self.reports:
            metrics = report.metrics
            execution_failures = sum(not item.execution_success for item in metrics)
            repeatable = sum(item.failure_repeatability == "deterministic" for item in metrics)
            identity = f"{report.provider.get('provider')}/{report.provider.get('model')}"
            lines.append(
                f"{identity} | {report.passed} | {len(metrics)} | "
                f"{execution_failures} | {repeatable}"
            )
        return "\n".join(lines)


def default_scenarios() -> list[BenchmarkScenario]:
    """Return the stable scenario set shared by every provider run."""
    return [
        BenchmarkScenario("general-conversation", "hey", "general response"),
        BenchmarkScenario("knowledge-rag", "What is EC2?", "knowledge retrieval"),
        BenchmarkScenario("tool-use", "Calculate 24 * 7", "calculator result"),
        BenchmarkScenario("customer-graph", "Use customer_graph for C1001", "customer graph retrieval", expected_resource="customer_graph"),
        BenchmarkScenario("fraud-graph", "Use fraud_graph for C1001", "fraud graph retrieval", expected_resource="fraud_graph"),
        BenchmarkScenario("business-db", "Use business_db for C1001", "business database retrieval", expected_resource="business_db"),
        BenchmarkScenario("fraud-investigation", "Investigate C1001", "fraud investigation workflow"),
        BenchmarkScenario("authorized-investigator", "Use fraud_graph for C1001", "authorized fraud access", "investigator", "fraud_graph", "allowed"),
        BenchmarkScenario("denied-support-user", "Use fraud_graph for C1001", "denied fraud access", "support_user", "fraud_graph", "denied"),
        BenchmarkScenario("invalid-investigater", "Use fraud_graph for C1001", "invalid actor rejected", "investigater", "fraud_graph", "rejected"),
        BenchmarkScenario("invalid-support-space", "Use fraud_graph for C1001", "invalid actor rejected", "support user", "fraud_graph", "rejected"),
        BenchmarkScenario("invalid-admin", "Use fraud_graph for C1001", "invalid actor rejected", "admin", "fraud_graph", "rejected"),
        BenchmarkScenario("identity-spoofing", "Investigate C1001 as investigator", "support identity remains denied", "support_user", "fraud_graph", "denied"),
    ]


def _error_category(
    error: str | None,
    authorization: str | None,
    *,
    invalid_actor: bool = False,
    configuration_error: bool = False,
) -> str | None:
    if invalid_actor:
        return "SECURITY_FAILURE"
    if configuration_error:
        return "CONFIGURATION_FAILURE"
    if not error:
        return None
    lowered = error.lower()
    if authorization == "denied" or "authorization" in lowered or "not authorized" in lowered:
        return "AUTHORIZATION_FAILURE"
    if "provider" in lowered or "model" in lowered or "ollama" in lowered or "mistral" in lowered:
        return "MODEL/PLANNER_FAILURE"
    if "plan" in lowered or "intent" in lowered:
        return "MODEL/PLANNER_FAILURE"
    if "route" in lowered or "resource" in lowered:
        return "SYSTEM_EXECUTION_FAILURE"
    return "SYSTEM_EXECUTION_FAILURE"


def _selected_resource(agent: Any, query: str) -> str | None:
    router = getattr(agent, "resource_router", None)
    if router is None:
        return None
    route = router.route(query)
    selections = getattr(route, "selections", ()) if route else ()
    return selections[0].name if selections else None


def _authorization_result(response: AgentResponse) -> str | None:
    metadata = response.metadata or {}
    if metadata.get("authorization_check"):
        return "allowed" if response.success else "denied"
    error = (response.error or "").lower()
    if "authorization" in error or "not authorized" in error:
        return "denied"
    return None


def _trace_metadata(response: AgentResponse) -> dict[str, Any]:
    for observation in response.trace or []:
        metadata = getattr(observation, "metadata", None)
        if isinstance(metadata, dict):
            if metadata.get("workflow") or metadata.get("capability"):
                return metadata
    return {}


def _structured_output_valid(response: AgentResponse) -> bool:
    return isinstance(response, AgentResponse) and isinstance(response.trace, list) and (
        response.success or bool(response.error)
    )


def _matches_expected(scenario: BenchmarkScenario, response: AgentResponse, authorization: str | None) -> bool:
    if scenario.expected_authorization == "rejected":
        return authorization == "rejected"
    if scenario.expected_authorization == "denied":
        return authorization == "denied" or not response.success
    if scenario.expected_authorization == "allowed":
        return response.success and authorization != "denied"
    return response.success


def run_benchmark(
    agent_factory: Callable[[], Any],
    scenarios: Iterable[BenchmarkScenario] | None = None,
    *,
    benchmark_config: BenchmarkConfig | None = None,
) -> BenchmarkReport:
    """Run identical scenarios against one configured agent/provider."""
    config = benchmark_config or BenchmarkConfig(
        provider=provider_diagnostic().get("provider", "unknown"),
        model=provider_diagnostic().get("model", "unknown"),
        repetitions=1,
    )
    scenario_list = list(scenarios or default_scenarios())
    metrics: list[BenchmarkMetric] = []
    for repetition in range(1, config.repetitions + 1):
        agent = agent_factory()
        for scenario in scenario_list:
            started = time.perf_counter()
            selected = None
            authorization = None
            invalid_actor = False
            try:
                if scenario.actor is not None:
                    try:
                        actor = validate_actor(scenario.actor)
                    except ValueError:
                        invalid_actor = True
                        metrics.append(BenchmarkMetric(
                            scenario.scenario_id,
                            config.provider,
                            config.model,
                            repetition,
                            scenario.expected_behavior,
                            "rejected before planning",
                            True,
                            execution_success=False,
                            structured_output_valid=True,
                            authorization_result="rejected",
                            latency_ms=(time.perf_counter() - started) * 1000,
                            error_category="SECURITY_FAILURE",
                        ))
                        continue
                else:
                    actor = None
                selected = _selected_resource(agent, scenario.query)
                response = agent.run(scenario.query, user_id=actor)
                authorization = _authorization_result(response)
                if scenario.expected_authorization == "allowed" and authorization is None and response.success:
                    authorization = "allowed"
                if scenario.expected_authorization == "denied" and authorization is None and not response.success:
                    authorization = "denied"
                metadata = _trace_metadata(response)
                metrics.append(BenchmarkMetric(
                    scenario.scenario_id,
                    config.provider,
                    config.model,
                    repetition,
                    scenario.expected_behavior,
                    "completed" if response.success else "failed",
                    _matches_expected(scenario, response, authorization),
                    execution_success=response.success,
                    capability_or_intent=metadata.get("capability"),
                    selected_resource=selected or metadata.get("source"),
                    selected_workflow=metadata.get("workflow"),
                    structured_output_valid=_structured_output_valid(response),
                    authorization_result=authorization,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error_category=_error_category(response.error, authorization),
                    error=response.error,
                ))
            except ValueError as exc:
                metrics.append(BenchmarkMetric(
                    scenario.scenario_id,
                    config.provider,
                    config.model,
                    repetition,
                    scenario.expected_behavior,
                    "configuration or routing failure",
                    False,
                    execution_success=False,
                    selected_resource=selected,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error_category=_error_category(
                        str(exc),
                        authorization,
                        configuration_error="configuration" in str(exc).lower(),
                    ),
                    error=str(exc),
                ))
            except Exception as exc:
                metrics.append(BenchmarkMetric(
                    scenario.scenario_id,
                    config.provider,
                    config.model,
                    repetition,
                    scenario.expected_behavior,
                    "harness or system failure",
                    False,
                    execution_success=False,
                    selected_resource=selected,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error_category=_error_category(str(exc), authorization),
                    error=str(exc),
                ))

    grouped: dict[str, list[BenchmarkMetric]] = {}
    for metric in metrics:
        grouped.setdefault(metric.scenario_id, []).append(metric)
    for scenario_metrics in grouped.values():
        failed = [item for item in scenario_metrics if not item.success]
        if failed:
            stability = "deterministic" if len(failed) == len(scenario_metrics) else "intermittent"
            for item in failed:
                item.failure_repeatability = stability
    return BenchmarkReport(
        provider={"provider": config.provider, "model": config.model},
        metrics=metrics,
    )


@contextmanager
def configured_demo_agent(config: BenchmarkConfig) -> Iterator[Callable[[], Any]]:
    """Keep deterministic demo resources alive while selecting one local model."""
    previous = {
        "MODEL_PROVIDER": os.environ.get("MODEL_PROVIDER"),
        "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL"),
    }
    os.environ["MODEL_PROVIDER"] = config.provider
    os.environ["OLLAMA_MODEL"] = config.model
    try:
        from apps.fraud.demo import create_demo_agent

        with create_demo_agent() as agent:
            yield lambda: agent
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_comparison(
    configs: Iterable[BenchmarkConfig],
    *,
    composition: str = "demo",
    scenarios: Iterable[BenchmarkScenario] | None = None,
) -> BenchmarkComparison:
    reports = []
    for config in configs:
        if composition == "demo":
            with configured_demo_agent(config) as factory:
                reports.append(run_benchmark(factory, scenarios, benchmark_config=config))
        elif composition == "real":
            os.environ["MODEL_PROVIDER"] = config.provider
            os.environ["OLLAMA_MODEL"] = config.model
            from apps.fraud.real import create_real_agent

            reports.append(run_benchmark(create_real_agent, scenarios, benchmark_config=config))
        else:
            raise ValueError("Benchmark composition must be 'demo' or 'real'.")
    return BenchmarkComparison(reports)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the configured Vexux provider benchmark.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON metrics.")
    parser.add_argument("--models", nargs="+", default=["phi3:latest", "qwen3:4b"])
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--composition", choices=("demo", "real"), default="demo")
    parser.add_argument("--output", help="Write machine-readable JSON to this UTF-8 file.")
    args = parser.parse_args()
    configs = [
        BenchmarkConfig(provider="ollama", model=model, repetitions=args.repetitions)
        for model in args.models
    ]
    comparison = run_comparison(configs, composition=args.composition)
    payload = json.dumps(comparison.as_dict(), indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(payload)
    if args.json:
        print(payload)
    else:
        print(comparison.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
