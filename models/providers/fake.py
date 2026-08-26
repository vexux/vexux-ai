"""Deterministic fake model provider for local testing and portability demos.

This lightweight provider implements the ModelProviderContract and returns a
predictable string response. It avoids any network dependency and is suitable
as a second provider implementation for Phase 27.
"""
from typing import Any


class FakeProvider:
    def __init__(self, model_name: str = "fake-model"):
        self._name = "fake"
        self.model_name = model_name

    @property
    def name(self) -> str:
        return self._name

    def generate(self, prompt: str, **kwargs) -> str:
        # Return a deterministic JSON-like response when the prompt requests JSON.
        # If the prompt mentions 'delegations' we return a small delegations plan.
        text = prompt or ""
        if "delegations" in text and "JSON" in text or 'delegations' in text:
            return '{"delegations": [{"id": "research", "agent": "research", "request": "Find relevant documents about X"}, {"id": "analysis", "agent": "analysis", "request": {"from_task": "research", "path": "output"}, "depends_on": ["research"]}]}'
        # Default fallback: echo the prompt in a safe wrapper
        return f"FAKE_RESPONSE: {text[:200]}"
