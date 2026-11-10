from core.config import load_config_from_env, provider_diagnostic


def test_core_composition_registers_qwen3_without_loading_rag_or_model(
    monkeypatch, tmp_path
):
    import core.composition as composition
    import models.providers.qwen3 as qwen3_module

    constructed = []

    class RecordingQwen3Provider:
        def __init__(self, *, model_path, max_input_tokens, max_new_tokens):
            constructed.append((model_path, max_input_tokens, max_new_tokens))
            self.name = "qwen3"
            self.metadata = {
                "provider": "qwen3",
                "model": "Qwen3-0.6B",
                "runtime_mode": "local",
            }

    def forbidden(*_args, **_kwargs):
        raise AssertionError("RAG must not initialize in this composition.")

    monkeypatch.setattr(qwen3_module, "Qwen3Provider", RecordingQwen3Provider)
    monkeypatch.setattr(composition, "RAGPipeline", forbidden)
    monkeypatch.setenv("MODEL_PROVIDER", "qwen3")
    monkeypatch.setenv("QWEN3_MODEL_PATH", str(tmp_path / "snapshot"))
    monkeypatch.setenv("QWEN3_MAX_INPUT_TOKENS", "512")
    monkeypatch.setenv("QWEN3_MAX_NEW_TOKENS", "64")
    monkeypatch.setenv("NEO4J_URI", "")
    monkeypatch.setenv("ENABLE_KNOWLEDGE_GRAPH", "0")
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", "")
    monkeypatch.setenv("ENABLE_AUTONOMOUS_DELEGATION", "0")
    monkeypatch.setenv("SQL_DATABASE_PATH", "")

    config = load_config_from_env()
    agent = composition.create_agent(enable_rag=False)

    assert constructed == [(str(tmp_path / "snapshot"), 512, 64)]
    assert agent.execution_manager.retrieval is None
    assert agent.execution_manager.model_gateway.provider_metadata() == {
        "provider": "qwen3",
        "model": "Qwen3-0.6B",
        "runtime_mode": "local",
    }
    assert provider_diagnostic(config)["model"] == "Qwen3-0.6B"
