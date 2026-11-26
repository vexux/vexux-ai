from dataclasses import dataclass
import logging

from fastapi.testclient import TestClient

from api.main import app, get_agent, get_real_agent
from core.contracts.observation import Observation
from core.contracts.response import AgentResponse


@dataclass
class FakeAgent:
    response: AgentResponse
    calls: list

    def run(self, query, session_id=None, user_id=None):
        self.calls.append({
            "query": query,
            "session_id": session_id,
            "user_id": user_id,
        })
        return self.response


def client_for(response):
    fake = FakeAgent(response=response, calls=[])
    app.dependency_overrides[get_agent] = lambda: fake
    return TestClient(app), fake


def teardown_function():
    app.dependency_overrides.clear()


def test_successful_request_response_structure():
    client, fake = client_for(AgentResponse(
        success=True,
        output="hello",
        trace=[],
        metadata={"request_id": "request-1", "session_id": None},
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "Hello"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "request-1",
        "session_id": None,
        "user_id": None,
        "success": True,
        "output": "hello",
        "error": None,
        "trace": [],
    }
    assert fake.calls == [{
        "query": "Hello",
        "session_id": None,
        "user_id": None,
    }]


def test_retrieval_request():
    client, fake = client_for(AgentResponse(
        success=True,
        output={"query": "EC2", "results": [], "context_found": True},
        metadata={"request_id": "request-rag", "session_id": "session-a"},
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "What is EC2?", "session_id": "session-a"},
    )

    assert response.status_code == 200
    assert response.json()["output"]["context_found"] is True
    assert fake.calls[0]["session_id"] == "session-a"


def test_tool_request():
    client, _ = client_for(AgentResponse(
        success=True,
        output=168,
        metadata={"request_id": "request-tool"},
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "Calculate 24 * 7"},
    )

    assert response.status_code == 200
    assert response.json()["output"] == 168


def test_multi_task_request_exposes_trace():
    trace = [
        Observation(
            success=True,
            output="EC2 context",
            summary="retrieval complete",
            task_id="task-1",
        ),
        Observation(
            success=True,
            output=168,
            summary="calculation complete",
            task_id="task-2",
        ),
    ]
    client, _ = client_for(AgentResponse(
        success=True,
        output="EC2 context and 168",
        trace=trace,
        metadata={"request_id": "request-multi"},
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "What is EC2 and calculate 24 * 7"},
    )

    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()["trace"]] == [
        "task-1",
        "task-2",
    ]


def test_invalid_request_is_controlled():
    client, fake = client_for(AgentResponse(success=True))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": ""},
    )

    assert response.status_code == 422
    assert fake.calls == []


def test_execution_failure_is_exposed_without_stack_trace():
    client, _ = client_for(AgentResponse(
        success=False,
        error="Agent could not complete the request.",
        trace=[],
        metadata={"request_id": "request-failure"},
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "Calculate invalid"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "Agent could not complete the request."
    assert "Traceback" not in response.text


def test_session_and_user_id_propagation():
    client, fake = client_for(AgentResponse(
        success=True,
        output="ok",
        metadata={
            "request_id": "request-session",
            "session_id": "session-a",
            "user_id": "user-a",
        },
    ))

    response = client.post(
        "/api/v1/agent/run",
        json={
            "query": "Follow up",
            "session_id": "session-a",
            "user_id": "user-a",
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "session-a"
    assert response.json()["user_id"] == "user-a"
    assert fake.calls[0] == {
        "query": "Follow up",
        "session_id": "session-a",
        "user_id": "user-a",
    }


def test_unhandled_agent_exception_is_generic_500():
    class ExplodingAgent:
        def run(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")

    app.dependency_overrides[get_agent] = lambda: ExplodingAgent()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/agent/run",
        json={"query": "Hello"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Agent execution failed."}
    assert "secret internal detail" not in response.text


def test_agent_logs_structured_task_observability(caplog):
    from agent.agent import Agent
    from agent.decision import DecisionMaker
    from agent.execution_manager import ExecutionManager
    from agent.observer import Observer
    from agent.planner import Planner
    from agent.response_synthesizer import ResponseSynthesizer
    from core.context.context_manager import ContextManager
    from core.tools.registry import ToolRegistry

    class Gateway:
        def generate(self, prompt, **kwargs):
            return '{"tasks": [{"id": "task-1", "description": "answer", "capability": "model", "input": {"query": "Hello"}}]}' if "planning component" in prompt else "ok"

    gateway = Gateway()
    agent = Agent(
        execution_manager=ExecutionManager(model_gateway=gateway),
        planner=Planner(gateway, ToolRegistry()),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=ResponseSynthesizer(gateway),
    )

    with caplog.at_level(logging.INFO, logger="agent.agent"):
        result = agent.run("Hello", session_id="session-log")

    assert result.success is True
    record = next(item for item in caplog.records if item.message == "agent.task.execution")
    assert record.request_id
    assert record.session_id == "session-log"
    assert record.task_id == "task-1"
    assert record.capability == "model"
    assert record.execution_success is True
    assert record.execution_duration_ms >= 0


def test_fraud_investigation_endpoint_uses_registered_real_workflow(monkeypatch):
    class StubWorkflow:
        def execute(self, workflow_input, context):
            from apps.fraud.domain import Customer, InvestigationResult
            return InvestigationResult(
                subject=Customer("C1001", "Alice Smith", "high"),
                findings=["2 open high-severity fraud alerts are associated with the customer."],
                risk_assessment="high",
                contributing_signals=["open_high_severity_alerts"],
                resources_consulted=["customer_graph", "fraud_graph", "business_db"],
            )

    class StubRegistry:
        def get(self, name):
            assert name == "fraud_investigation"
            return StubWorkflow()

    class StubRealAgent:
        workflow_registry = StubRegistry()

    import api.main as main_module
    monkeypatch.setattr(main_module, "get_real_agent", lambda: StubRealAgent())
    try:
        response = TestClient(app).post(
            "/api/v1/fraud/investigate",
            json={"query": "Investigate C1001", "session_id": "session-fraud", "user_id": "investigator"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["session_id"] == "session-fraud"
        assert body["investigation"]["summary"]["customer_id"] == "C1001"
        assert body["investigation"]["summary"]["risk_assessment"] == "high"
        assert body["metadata"]["workflow"] == "fraud_investigation"
    finally:
        app.dependency_overrides.clear()


def test_get_real_agent_calls_real_composition(monkeypatch):
    import api.main as main_module

    sentinel = object()
    main_module.get_real_agent.cache_clear()
    monkeypatch.setattr(main_module, "create_real_agent", lambda: sentinel)
    try:
        assert main_module.get_real_agent() is sentinel
    finally:
        main_module.get_real_agent.cache_clear()


def test_fraud_payload_adds_sqlite_evidence_and_keeps_mysql_compatibility():
    from apps.fraud.domain import Customer, InvestigationResult
    import api.main as main_module

    result = InvestigationResult(Customer("C1001", "Alice Smith"), risk_assessment="high")
    payload = main_module._build_investigation_payload(result, "request-1")

    assert payload["sqlite"] == {
        "transactions": [],
        "fraud_alerts": [],
        "investigation_records": [],
    }
    assert payload["mysql"] == payload["sqlite"]


def test_missing_customer_id_is_rejected_for_investigation(monkeypatch):
    class StubRealAgent:
        workflow_registry = object()

    import api.main as main_module
    monkeypatch.setattr(main_module, "get_real_agent", lambda: StubRealAgent())
    response = TestClient(app).post(
        "/api/v1/fraud/investigate",
        json={"query": "Investigate this account for suspicious activity", "session_id": "missing-customer", "user_id": "investigator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "customer ID is required" in body["error"]


def test_unknown_customer_is_returned_as_authoritative_not_found(monkeypatch):
    from core.contracts.workflow import WorkflowExecutionError

    class StubWorkflow:
        def execute(self, workflow_input, context):
            raise WorkflowExecutionError(
                "The requested customer was not found in the authoritative customer graph.",
                terminal=True,
                retryable=False,
                authoritative=True,
                failure_category="not_found",
            )

    class StubRegistry:
        def get(self, name):
            return StubWorkflow()

    class StubRealAgent:
        workflow_registry = StubRegistry()

    import api.main as main_module
    monkeypatch.setattr(main_module, "get_real_agent", lambda: StubRealAgent())
    response = TestClient(app).post(
        "/api/v1/fraud/investigate",
        json={"query": "Investigate C9999", "session_id": "unknown-customer", "user_id": "investigator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"]
    assert body["metadata"]["failure_category"] == "not_found"
