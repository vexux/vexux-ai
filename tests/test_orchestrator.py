from core.contracts.response import AgentResponse
from core.orchestrator import Orchestrator


class DummyAgent:
    def __init__(self, *, run_result=None, workflow_result=None):
        self.run_result = run_result
        self.workflow_result = workflow_result
        self.calls = []

    def run(self, query, session_id=None, user_id=None):
        self.calls.append(("run", query, session_id, user_id))
        if self.run_result is not None:
            return self.run_result
        return AgentResponse(
            success=True,
            output=f"agent:{query}",
            metadata={"selected_mode": "agent"},
        )

    def run_workflow(self, workflow_name, workflow_input=None, session_id=None, user_id=None):
        self.calls.append(("workflow", workflow_name, workflow_input, session_id, user_id))
        if self.workflow_result is not None:
            return self.workflow_result
        return AgentResponse(
            success=True,
            output=f"workflow:{workflow_name}",
            metadata={"selected_mode": "workflow", "workflow_name": workflow_name},
        )


class DummyWorkflowRegistry:
    def __init__(self, *names):
        self.names = set(names)

    def get(self, name):
        if name not in self.names:
            raise KeyError(name)
        return object()


def test_orchestrator_routes_normal_agent_mode():
    agent = DummyAgent()
    orchestrator = Orchestrator(agent)

    result = orchestrator.run({"query": "hello there"}, session_id="s1", user_id="u1")

    assert result.success is True
    assert result.output == "agent:hello there"
    assert agent.calls == [("run", "hello there", "s1", "u1")]


def test_orchestrator_routes_workflow_mode():
    agent = DummyAgent()
    registry = DummyWorkflowRegistry("knowledge-grounded-answer")
    orchestrator = Orchestrator(agent, workflow_registry=registry)

    result = orchestrator.run(
        {
            "workflow": "knowledge-grounded-answer",
            "topic": "policy",
            "query": "Explain the policy",
        },
        session_id="s2",
        user_id="u2",
    )

    assert result.success is True
    assert result.output == "workflow:knowledge-grounded-answer"
    assert agent.calls == [
        ("workflow", "knowledge-grounded-answer", {"topic": "policy"}, "s2", "u2")
    ]


def test_orchestrator_rejects_unknown_workflow():
    agent = DummyAgent()
    registry = DummyWorkflowRegistry("known")
    orchestrator = Orchestrator(agent, workflow_registry=registry)

    result = orchestrator.run({"workflow": "missing", "query": "hello"})

    assert result.success is False
    assert result.error == "Unknown workflow: missing"
    assert result.metadata == {"selected_mode": "workflow", "workflow_name": "missing"}
    assert agent.calls == []


def test_orchestrator_returns_underlying_agent_failure():
    agent = DummyAgent(
        run_result=AgentResponse(
            success=False,
            error="agent exploded",
            metadata={"selected_mode": "agent"},
        )
    )
    orchestrator = Orchestrator(agent)

    result = orchestrator.run("hello")

    assert result.success is False
    assert result.error == "agent exploded"
    assert result.metadata == {"selected_mode": "agent"}


def test_orchestrator_preserves_legacy_agent_run_compatibility():
    agent = DummyAgent()
    orchestrator = Orchestrator(agent)

    result = orchestrator.run("legacy query", session_id="legacy-session", user_id="legacy-user")

    assert result.success is True
    assert result.output == "agent:legacy query"
    assert agent.calls == [("run", "legacy query", "legacy-session", "legacy-user")]
