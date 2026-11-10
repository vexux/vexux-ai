from contextlib import contextmanager
import os
from types import SimpleNamespace

import pytest

from core.model_gateway.gateway import ModelGateway
from models.providers.fake import FakeProvider
from scripts.manual import run_agent


class StubStore:
    def recent(self, *args, **kwargs):
        return []

    def aggregate_metrics(self):
        return {
            "total_requests": 2,
            "successes": 2,
            "failures": 0,
            "authorization_denials": 0,
            "average_duration_ms": 1.0,
        }


class StubAgent:
    def __init__(self, fail_on=None):
        self.execution_manager = SimpleNamespace(
            model_gateway=ModelGateway(FakeProvider("terminal-test"))
        )
        self.resource_router = SimpleNamespace(route=lambda query: None)
        self.calls = []
        self.fail_on = fail_on

    def run(self, query, *, session_id, user_id):
        self.calls.append((query, session_id, user_id))
        if query == self.fail_on:
            raise RuntimeError("provider failed")
        return SimpleNamespace(
            output=f"{user_id}: {query}",
            error=None,
            metadata={},
        )


@pytest.fixture
def isolated_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(run_agent, "get_observability_store", lambda *_args: StubStore())
    monkeypatch.setattr(
        run_agent,
        "get_config",
        lambda: SimpleNamespace(
            model_provider="qwen3",
            observability_db_path=str(tmp_path / "observability.db"),
        ),
    )


@pytest.mark.parametrize("provider", ["fake", "qwen3", "llama_cpp"])
def test_synthetic_selection_reuses_demo_factory_and_restores_environment(
    monkeypatch, provider
):
    observed = []
    agent = StubAgent()

    @contextmanager
    def demo_factory(*, enable_rag):
        observed.append(
            (
                enable_rag,
                os.environ["MODEL_PROVIDER"],
                os.environ["NEO4J_URI"],
                os.environ["ENABLE_KNOWLEDGE_GRAPH"],
                os.environ["ENABLE_LOCAL_RAG_INFERENCE"],
                os.environ["PERSISTENT_MEMORY_DB"],
                os.environ["ENABLE_AUTONOMOUS_DELEGATION"],
                os.environ["SQL_DATABASE_PATH"],
                os.environ.get("LLAMA_CPP_MODEL_PATH"),
                os.environ.get("LLAMA_CPP_N_CTX"),
                os.environ.get("LLAMA_CPP_N_THREADS"),
                os.environ.get("LLAMA_CPP_MAX_NEW_TOKENS"),
            )
        )
        yield agent

    monkeypatch.setattr(run_agent, "create_demo_agent", demo_factory)
    monkeypatch.setenv("NEO4J_URI", "restore-this-value")
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("LLAMA_CPP_MODEL_PATH", "restore-model.gguf")
    monkeypatch.setenv("LLAMA_CPP_N_CTX", "3072")
    monkeypatch.setenv("LLAMA_CPP_N_THREADS", "6")
    monkeypatch.setenv("LLAMA_CPP_MAX_NEW_TOKENS", "192")
    args = SimpleNamespace(
        composition="synthetic",
        provider=provider,
        qwen3_model_path="C:/local/qwen3" if provider == "qwen3" else None,
        qwen3_max_input_tokens=512 if provider == "qwen3" else None,
        qwen3_max_new_tokens=64 if provider == "qwen3" else None,
        llama_cpp_model_path="C:/local/llama.gguf" if provider == "llama_cpp" else None,
        llama_cpp_n_ctx=1024 if provider == "llama_cpp" else None,
        llama_cpp_n_threads=3 if provider == "llama_cpp" else None,
        llama_cpp_max_new_tokens=128 if provider == "llama_cpp" else None,
    )

    with run_agent._selected_agent(args) as selected:
        assert selected is agent

    assert observed == [
        (
            False,
            provider,
            "",
            "0",
            "0",
            "",
            "0",
            "",
            "C:/local/llama.gguf" if provider == "llama_cpp" else "restore-model.gguf",
            "1024" if provider == "llama_cpp" else "3072",
            "3" if provider == "llama_cpp" else "6",
            "128" if provider == "llama_cpp" else "192",
        )
    ]
    assert os.environ["MODEL_PROVIDER"] == "ollama"
    assert os.environ["NEO4J_URI"] == "restore-this-value"
    assert os.environ["LLAMA_CPP_MODEL_PATH"] == "restore-model.gguf"
    assert os.environ["LLAMA_CPP_N_CTX"] == "3072"
    assert os.environ["LLAMA_CPP_N_THREADS"] == "6"
    assert os.environ["LLAMA_CPP_MAX_NEW_TOKENS"] == "192"


def test_synthetic_terminal_preserves_queries_actor_switching_metrics_and_exit(
    monkeypatch, capsys, isolated_terminal
):
    agent = StubAgent()
    inputs = iter(
        [
            "/actor investigator",
            "Investigate C1001",
            "/actor support_user",
            "Investigate C1002",
            "/metrics",
            "exit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    run_agent._run_terminal(agent, "synthetic")

    output = capsys.readouterr().out
    assert "Provider: fake" in output
    assert "Synthetic mode:" in output
    assert "requests=2 successes=2" in output
    assert "Exiting..." in output
    assert agent.calls == [
        ("Investigate C1001", "terminal-session", "investigator"),
        ("Investigate C1002", "terminal-session", "support_user"),
    ]


def test_synthetic_terminal_handles_provider_error_and_continues(
    monkeypatch, capsys, isolated_terminal
):
    agent = StubAgent(fail_on="Explain C1001")
    inputs = iter(["Explain C1001", "Investigate C1001", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    run_agent._run_terminal(agent, "synthetic")

    output = capsys.readouterr().out
    assert "could not complete the request" in output
    assert "investigator: Investigate C1001" in output
    assert "Exiting..." in output


def test_real_composition_remains_the_default_and_unchanged(monkeypatch):
    agent = StubAgent()
    observed = []

    monkeypatch.setattr(
        run_agent,
        "create_real_agent",
        lambda: (observed.append("real") or agent),
    )
    args = SimpleNamespace(
        composition="real",
        provider=None,
        qwen3_model_path=None,
        qwen3_max_input_tokens=None,
        qwen3_max_new_tokens=None,
        llama_cpp_model_path=None,
        llama_cpp_n_ctx=None,
        llama_cpp_n_threads=None,
        llama_cpp_max_new_tokens=None,
    )

    with run_agent._selected_agent(args) as selected:
        assert selected is agent
    assert observed == ["real"]


@pytest.mark.parametrize(
    ("provider", "expected_name"),
    [("fake", "fake"), ("qwen3", "qwen3"), ("llama_cpp", "llama_cpp")],
)
def test_actual_synthetic_composition_disables_rag_and_remote_databases(
    monkeypatch, provider, expected_name
):
    import core.composition as core_composition

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Synthetic composition must not construct this resource.")

    monkeypatch.setattr(core_composition, "RAGPipeline", forbidden)
    monkeypatch.setattr(core_composition, "Neo4jKnowledgeGraph", forbidden)
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEO4J_URI", "not-used")
    monkeypatch.setenv("ENABLE_KNOWLEDGE_GRAPH", "1")
    monkeypatch.setenv("ENABLE_LOCAL_RAG_INFERENCE", "1")
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", "not-used")
    monkeypatch.setenv("ENABLE_AUTONOMOUS_DELEGATION", "1")
    args = SimpleNamespace(
        composition="synthetic",
        provider=provider,
        qwen3_model_path=None,
        qwen3_max_input_tokens=None,
        qwen3_max_new_tokens=None,
    )

    with run_agent._selected_agent(args) as agent:
        assert agent.execution_manager.retrieval is None
        assert agent.execution_manager.model_gateway.provider.name == expected_name
        assert [
            resource.name for resource in agent.resource_router._resources()
        ] == ["customer_graph", "fraud_graph", "business_db"]
