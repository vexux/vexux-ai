import os
from pathlib import Path
from core.composition import create_agent


def test_create_agent_without_memory_env(monkeypatch):
    # Ensure env var not set
    monkeypatch.delenv("PERSISTENT_MEMORY_DB", raising=False)
    # Provide a dummy API key so create_agent can initialize the configured provider in tests
    monkeypatch.setenv("MISTRAL_API_KEY", "test")
    agent = create_agent()
    # Agent must have attribute memory_registry but it can be None
    assert hasattr(agent, "memory_registry")
    assert agent.memory_registry is None


def test_create_agent_with_memory_env(tmp_path, monkeypatch):
    dbpath = tmp_path / "mem.db"
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", str(dbpath))
    # Provide a dummy API key so create_agent can initialize the configured provider in tests
    monkeypatch.setenv("MISTRAL_API_KEY", "test")
    agent = create_agent()
    assert agent.memory_registry is not None
    registry = agent.memory_registry
    # registry must provide a memory backend
    mem = registry.get()
    mem_id = mem.store("scope-a", "my favorite language is Python")
    results = mem.retrieve("scope-a", "Python")
    assert len(results) >= 1
    assert results[0]["memory_id"] == mem_id
    # cleanup env var
    monkeypatch.delenv("PERSISTENT_MEMORY_DB", raising=False)
