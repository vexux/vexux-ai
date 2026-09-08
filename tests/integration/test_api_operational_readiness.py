from fastapi.testclient import TestClient

from api.main import app, get_agent, get_orchestrator


class StubAgent:
    def run(self, query, session_id=None, user_id=None):
        from core.contracts.response import AgentResponse

        return AgentResponse(
            success=True,
            output={"query": query, "authorization": "Bearer synthetic-token"},
            metadata={"request_id": "api-request", "session_id": session_id, "user_id": user_id},
        )


class StubOrchestrator:
    def run(self, request, session_id=None, user_id=None):
        from core.contracts.response import AgentResponse

        return AgentResponse(
            success=False,
            error="Unauthorized access to knowledge graph: fraud_graph",
            metadata={"request_id": "orchestration-request", "orchestration_id": "orch-1"},
        )


def test_agent_endpoint_serializes_and_redacts_response():
    app.dependency_overrides[get_agent] = lambda: StubAgent()
    try:
        response = TestClient(app).post(
            "/api/v1/agent/run",
            json={"query": "synthetic request", "session_id": "s1", "user_id": "u1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == "api-request"
        assert "synthetic-token" not in str(body)
        assert body["success"] is True
    finally:
        app.dependency_overrides.clear()


def test_orchestrator_endpoint_preserves_controlled_failure():
    app.dependency_overrides[get_orchestrator] = lambda: StubOrchestrator()
    try:
        response = TestClient(app).post(
            "/api/v1/orchestrator/run",
            json={"query": "synthetic investigation", "user_id": "support_user"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["orchestration_id"] == "orch-1"
        assert body["success"] is False
        assert "Unauthorized access" in body["error"]
    finally:
        app.dependency_overrides.clear()


def test_health_and_readiness_endpoints(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    readiness = client.get("/ready")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"


def test_ollama_is_a_supported_readiness_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "model_provider": "ollama"}
