from contextlib import contextmanager
import os
from types import SimpleNamespace

from apps.fraud import demo_cli


def test_demo_cli_uses_fake_provider_and_disables_external_resources(
    monkeypatch, capsys
):
    observed_environment = {}

    class FakeAgent:
        def run(self, query, user_id):
            assert query == "Investigate C1001"
            assert user_id == "investigator"
            return SimpleNamespace(
                success=True,
                output=(
                    "C1001 Investigation\nRisk: HIGH\nFindings:\n"
                    "- Open high-severity alert\nResources consulted:\n"
                    "customer_graph, business_db, fraud_graph"
                ),
                error=None,
            )

    @contextmanager
    def create_agent():
        observed_environment.update(
            {
                key: os.environ.get(key)
                for key in demo_cli._SAFE_DEMO_ENVIRONMENT
            }
        )
        yield FakeAgent()

    monkeypatch.setattr(demo_cli, "create_demo_agent", create_agent)
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEO4J_URI", "configured-but-not-used")
    monkeypatch.setenv("ENABLE_KNOWLEDGE_GRAPH", "1")
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", "existing-path")

    assert demo_cli.main(["C1001", "--provider", "fake"]) == 0

    output = capsys.readouterr().out
    assert "Status: SUCCESS" in output
    assert "Risk: HIGH" in output
    assert "customer_graph, business_db, fraud_graph" in output
    assert observed_environment == {
        "MODEL_PROVIDER": "fake",
        "NEO4J_URI": "",
        "ENABLE_KNOWLEDGE_GRAPH": "0",
        "ENABLE_LOCAL_RAG_INFERENCE": "0",
        "ENABLE_AUTONOMOUS_DELEGATION": "0",
        "PERSISTENT_MEMORY_DB": "",
        "SQL_DATABASE_PATH": "",
    }
    assert os.environ["MODEL_PROVIDER"] == "ollama"
    assert os.environ["NEO4J_URI"] == "configured-but-not-used"


def test_demo_cli_reports_failure_and_returns_nonzero(monkeypatch, capsys):
    class FailedAgent:
        def run(self, query, user_id):
            return SimpleNamespace(
                success=False,
                output=None,
                error="Synthetic investigation failed.",
            )

    @contextmanager
    def create_agent():
        yield FailedAgent()

    monkeypatch.setattr(demo_cli, "create_demo_agent", create_agent)

    assert demo_cli.main(["C1002"]) == 1
    output = capsys.readouterr().out
    assert "Status: FAILURE" in output
    assert "Synthetic investigation failed." in output
