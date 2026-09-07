"""Deterministic fake model provider for local testing and portability demos."""
import json
import re


class FakeProvider:
    def __init__(self, model_name: str = "fake-model"):
        self._name = "fake"
        self.model_name = model_name

    @property
    def name(self) -> str:
        return self._name

    def generate(self, prompt: str, **kwargs) -> str:
        text = prompt or ""
        normalized = text.lower()

        if "delegation" in normalized and "json" in normalized:
            return json.dumps({
                "delegations": [
                    {
                        "id": "research",
                        "agent": "research",
                        "request": "Find relevant information for the user request",
                    },
                    {
                        "id": "analysis",
                        "agent": "analysis",
                        "request": {"from_task": "research", "path": "output"},
                        "depends_on": ["research"],
                    },
                ]
            })

        if "classify the user request" in normalized and "intent" in normalized:
            return json.dumps({
                "intent": "general",
                "confidence": 1.0,
                "entities": {},
            })

        if "structured planning component" in normalized or "structured recovery-planning component" in normalized:
            query = self._extract_user_request(text)
            return json.dumps({
                "tasks": [
                    {
                        "id": self._extract_task_id(text) or "task_1",
                        "description": "Answer the user's request",
                        "capability": "model",
                        "input": {"query": query},
                    }
                ]
            })

        return f"FAKE_RESPONSE: {text[:200]}"

    @staticmethod
    def _extract_user_request(prompt: str) -> str:
        match = re.search(
            r"User request:\s*(.*?)(?:\n\s*(?:Previous conversation context|Registered tools|"
            r"Registered knowledge sources|Registered workflows|Failed task ID|$))",
            prompt,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            request = match.group(1).strip()
            if request:
                return request
        return "Answer the user's request"

    @staticmethod
    def _extract_task_id(prompt: str) -> str | None:
        match = re.search(r"Failed task ID \(YOU MUST PRESERVE THIS EXACT ID\):\s*([^\s]+)", prompt)
        return match.group(1) if match else None
