"""Centralized configuration parsing and validation.

Provides a small Config dataclass and helper functions to parse environment
variables consistently across the application. This module intentionally
avoids including secrets in repr/serialization.
"""
from dataclasses import dataclass, field
import os
from typing import Optional


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    val = str(value).strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off", ""):
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_int(value: Optional[str], default: int, min_value: int = 1, max_value: Optional[int] = None) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        v = int(value)
    except Exception as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc
    if v < min_value:
        raise ValueError(f"Integer value {v} below minimum {min_value}")
    if max_value is not None and v > max_value:
        raise ValueError(f"Integer value {v} exceeds maximum {max_value}")
    return v


@dataclass
class Config:
    model_provider: str = "mistral"
    autonomous_delegation_enabled: bool = False
    max_autonomous_delegations: int = 4
    max_parallel_tasks: int = 1
    persistent_memory_db: Optional[str] = None
    knowledge_graph_enabled: bool = False
    neo4j_uri: Optional[str] = None
    neo4j_username: Optional[str] = None
    neo4j_password: Optional[str] = None
    neo4j_database: Optional[str] = None
    neo4j_graph_name: str = "neo4j"
    sql_database_path: Optional[str] = None
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "vexux_app"
    mysql_password: Optional[str] = None
    mysql_database: str = "vexux_fraud"
    local_rag_inference_enabled: bool = False

    # Hide potential secrets from default repr by overriding
    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"Config(model_provider={self.model_provider!r}, "
            f"autonomous_delegation_enabled={self.autonomous_delegation_enabled!r}, "
            f"max_autonomous_delegations={self.max_autonomous_delegations!r}, "
            f"max_parallel_tasks={self.max_parallel_tasks!r}, "
            f"persistent_memory_db={'<set>' if self.persistent_memory_db else None}, "
            f"knowledge_graph_enabled={self.knowledge_graph_enabled!r})"
        )


def load_config_from_env(prefix: str = "") -> Config:
    """Load configuration from environment variables.

    prefix may be used by callers to namespace variables (unused by default).
    """
    def e(name: str) -> Optional[str]:
        return os.getenv(prefix + name)

    model_provider = e("MODEL_PROVIDER") or "mistral"

    autonomous_delegation_enabled = _parse_bool(e("ENABLE_AUTONOMOUS_DELEGATION"))

    max_autonomous_delegations = _parse_int(e("MAX_AUTONOMOUS_DELEGATIONS"), default=4, min_value=1, max_value=32)

    max_parallel_tasks = _parse_int(e("AGENT_MAX_PARALLEL_TASKS"), default=1, min_value=1, max_value=32)

    persistent_memory_db = e("PERSISTENT_MEMORY_DB") or None

    knowledge_graph_enabled = _parse_bool(e("ENABLE_KNOWLEDGE_GRAPH"))
    neo4j_uri = e("NEO4J_URI") or None
    neo4j_username = e("NEO4J_USERNAME") or None
    neo4j_password = e("NEO4J_PASSWORD") or None
    neo4j_database = e("NEO4J_DATABASE") or None
    neo4j_graph_name = e("NEO4J_GRAPH_NAME") or "neo4j"
    sql_database_path = e("SQL_DATABASE_PATH") or None
    mysql_host = e("MYSQL_HOST") or "127.0.0.1"
    mysql_port = _parse_int(e("MYSQL_PORT"), default=3306, min_value=1, max_value=65535)
    mysql_user = e("MYSQL_USER") or "vexux_app"
    mysql_password = e("MYSQL_PASSWORD") or None
    mysql_database = e("MYSQL_DATABASE") or "vexux_fraud"
    local_rag_inference_enabled = _parse_bool(e("ENABLE_LOCAL_RAG_INFERENCE"))

    return Config(
        model_provider=model_provider.lower(),
        autonomous_delegation_enabled=autonomous_delegation_enabled,
        max_autonomous_delegations=max_autonomous_delegations,
        max_parallel_tasks=max_parallel_tasks,
        persistent_memory_db=persistent_memory_db,
        knowledge_graph_enabled=knowledge_graph_enabled,
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        neo4j_graph_name=neo4j_graph_name,
        sql_database_path=sql_database_path,
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_user=mysql_user,
        mysql_password=mysql_password,
        mysql_database=mysql_database,
        local_rag_inference_enabled=local_rag_inference_enabled,
    )


# Cache config keyed by a snapshot of relevant environment variables.
_cached_config: Optional[Config] = None
_cached_env_snapshot: Optional[tuple] = None


def _env_snapshot(prefix: str = "") -> tuple:
    keys = [
        "MODEL_PROVIDER",
        "ENABLE_AUTONOMOUS_DELEGATION",
        "MAX_AUTONOMOUS_DELEGATIONS",
        "AGENT_MAX_PARALLEL_TASKS",
        "PERSISTENT_MEMORY_DB",
        "ENABLE_KNOWLEDGE_GRAPH",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "NEO4J_GRAPH_NAME",
        "SQL_DATABASE_PATH",
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
        "ENABLE_LOCAL_RAG_INFERENCE",
    ]
    return tuple(os.getenv(prefix + k) for k in keys)


def get_config() -> Config:
    global _cached_config, _cached_env_snapshot
    snapshot = _env_snapshot()
    if _cached_config is not None and _cached_env_snapshot == snapshot:
        return _cached_config
    # Otherwise reload and update cache
    cfg = load_config_from_env()
    _cached_config = cfg
    _cached_env_snapshot = snapshot
    return cfg
