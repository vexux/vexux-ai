import os
import pytest
from core.config import load_config_from_env, _parse_bool, _parse_int, get_config


def test_default_config(monkeypatch):
    # Ensure no env variables
    for k in ["MODEL_PROVIDER","ENABLE_AUTONOMOUS_DELEGATION","MAX_AUTONOMOUS_DELEGATIONS","AGENT_MAX_PARALLEL_TASKS","PERSISTENT_MEMORY_DB","ENABLE_KNOWLEDGE_GRAPH","ENABLE_LOCAL_RAG_INFERENCE"]:
        monkeypatch.delenv(k, raising=False)
    cfg = load_config_from_env()
    assert cfg.model_provider == "mistral"
    assert cfg.autonomous_delegation_enabled is False
    assert cfg.max_autonomous_delegations == 4
    assert cfg.max_parallel_tasks == 1
    assert cfg.persistent_memory_db is None
    assert cfg.knowledge_graph_enabled is False
    assert cfg.local_rag_inference_enabled is False


def test_local_rag_inference_is_explicitly_configured(monkeypatch):
    monkeypatch.setenv("ENABLE_LOCAL_RAG_INFERENCE", "1")
    assert load_config_from_env().local_rag_inference_enabled is True


def test_boolean_parsing_true_values():
    for val in ("1","true","yes","on","TRUE","Yes"):
        assert _parse_bool(val) is True


def test_boolean_parsing_false_values():
    for val in (None, "0","false","no","off",""):
        assert _parse_bool(val) is False


def test_boolean_parsing_invalid():
    with pytest.raises(ValueError):
        _parse_bool("notabool")


def test_int_parsing_and_bounds():
    assert _parse_int("5", default=4, min_value=1, max_value=10) == 5
    assert _parse_int(None, default=3, min_value=1, max_value=10) == 3
    with pytest.raises(ValueError):
        _parse_int("-1", default=1, min_value=1, max_value=10)
    with pytest.raises(ValueError):
        _parse_int("100", default=1, min_value=1, max_value=10)
    with pytest.raises(ValueError):
        _parse_int("notint", default=1)


def test_get_config_caching(monkeypatch):
    # Ensure get_config returns a Config instance and caching works
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    cfg1 = get_config()
    cfg2 = get_config()
    assert cfg1 is cfg2
