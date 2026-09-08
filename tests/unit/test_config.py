import os
import pytest
from core.config import load_config_from_env, _parse_bool, _parse_int, get_config
import core.config as config_module


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


def test_local_env_values_are_loaded_without_mutating_process_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL_PROVIDER=mistral\nMISTRAL_API_KEY=local-key\nMYSQL_PASSWORD=local-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_ENV_FILE", env_file)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)

    cfg = load_config_from_env()

    assert cfg.model_provider == "mistral"
    assert cfg.mistral_api_key == "local-key"
    assert cfg.mysql_password == "local-secret"
    assert os.getenv("MYSQL_PASSWORD") is None
    assert "local-secret" not in repr(cfg)
    assert "local-key" not in repr(cfg)


def test_process_environment_overrides_local_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL_PROVIDER=fake\nMYSQL_HOST=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_ENV_FILE", env_file)
    monkeypatch.setenv("MODEL_PROVIDER", "mistral")
    monkeypatch.setenv("MYSQL_HOST", "from-process")

    cfg = load_config_from_env()

    assert cfg.model_provider == "mistral"
    assert cfg.mysql_host == "from-process"


def test_fresh_process_loads_dotenv_configuration(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL_PROVIDER=fake\nNEO4J_URI=bolt://fresh-process\n"
        "NEO4J_USERNAME=fresh-user\nNEO4J_PASSWORD=fresh-secret\n"
        "MYSQL_PASSWORD=mysql-secret\nMISTRAL_API_KEY=mistral-secret\n",
        encoding="utf-8",
    )
    script = (
        "from pathlib import Path\n"
        "import core.config as config\n"
        f"config._ENV_FILE = Path(r'{env_file}')\n"
        "value = config.load_config_from_env()\n"
        "assert value.neo4j_uri == 'bolt://fresh-process'\n"
        "assert value.mysql_password == 'mysql-secret'\n"
        "assert value.mistral_api_key == 'mistral-secret'\n"
        "print(value.model_provider, 'credentials-loaded')\n"
    )
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "fake credentials-loaded"
    assert "fresh-secret" not in result.stdout
    assert "mistral-secret" not in result.stdout


def test_missing_real_credentials_are_reported_by_real_composition(monkeypatch):
    from apps.fraud.real import create_real_agent

    for name in (
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "MYSQL_PASSWORD",
    ):
        monkeypatch.setenv(name, "")

    with pytest.raises(ValueError, match="NEO4J_URI must be configured"):
        create_real_agent()


def test_dotenv_mistral_configuration_selects_mistral_provider(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL_PROVIDER=mistral\nMISTRAL_API_KEY=local-key\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_ENV_FILE", env_file)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    from core.composition import create_agent

    agent = create_agent()

    assert agent.planner.model_gateway.provider.name == "mistral"
