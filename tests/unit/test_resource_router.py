import pytest

from apps.fraud.composition import build_fraud_investigation_graphs
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.resource_router import ResourceRouter
from core.knowledge.sql_source import SQLKnowledgeSource
from agent.agent import Agent
from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, ExecutionResult, Plan, Task
from core.context.context_manager import ContextManager
from agent.observer import Observer
from agent.decision import DecisionMaker
from core.contracts.progress import ProgressReporter
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph


class StubBackend:
    def execute(self, query, parameters=None):
        return []


class RecordingExecutionManager:
    def __init__(self):
        self.calls = []

    def execute(self, task, context):
        self.calls.append(task)
        return ExecutionResult(success=True, output={"evidence": None})


class FailingPlanner:
    def create_plan(self, *args, **kwargs):
        raise AssertionError("explicit resource routing must bypass Planner")


class StaticSynthesizer:
    def synthesize(self, query, observations, conversation_context=None):
        return "ok"

    def synthesize_authorization(self, requests, decisions):
        return "\n".join(
            f"{request.resource_name} -> {'ALLOWED' if decision.allowed else 'DENIED'}"
            for request, decision in zip(requests, decisions)
        )


from core.policy.default import DefaultPolicy


class ActorPolicy(DefaultPolicy):
    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        from core.policy.default import PolicyDecision
        return PolicyDecision(
            allowed=not (actor == "support_user" and resource_name == "fraud_graph"),
            reason="denied by test policy",
            policy_name="test_policy",
        )


def router():
    sources = KnowledgeSourceRegistry()
    source = SQLKnowledgeSource(
        StubBackend(),
        default_query="SELECT * FROM accounts WHERE customer_id = ?",
        aliases=("sqlite", "sqlite db", "sqlite database"),
    )
    source.name = "business_db"
    sources.register(source)
    return ResourceRouter(sources, build_fraud_investigation_graphs())


def test_routes_single_and_multiple_registered_resources():
    result = router().route("read from fraud graph")
    assert [item.name for item in result.selections] == ["fraud_graph"]
    result = router().route("customer graph, fraud graph and sqlite db for C1001")
    assert [item.name for item in result.selections] == ["customer_graph", "fraud_graph", "business_db"]
    assert len(result.graph_requests) == 2
    assert result.source_tasks[0]["parameters"] == ("C1001",)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("TELL ME data from customer knowledge graph", ["customer_graph"]),
        ("TELL ME data from fraud knowledge graphs", ["fraud_graph"]),
        ("data from sqlite database", ["business_db"]),
        ("Customer Graph and customer_graph", ["customer_graph"]),
        ("CUSTOMER GRAPH and FRAUD GRAPH and SQLITE DB", ["customer_graph", "fraud_graph", "business_db"]),
        ("customer and fraud knowledge graphs", ["customer_graph", "fraud_graph"]),
    ],
)
def test_routes_metadata_aliases_case_insensitively_and_deduplicates(query, expected):
    result = router().route(query)
    assert [item.name for item in result.selections] == expected


def test_no_resource_preserves_default_and_unknown_is_controlled():
    assert router().route("hello there") is None
    with pytest.raises(ValueError, match="Unknown or unavailable"):
        router().route("read from payroll_graph")


def test_agent_run_uses_explicit_resources_without_planner():
    manager = RecordingExecutionManager()
    agent = Agent(
        execution_manager=manager,
        planner=FailingPlanner(),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=StaticSynthesizer(),
        resource_router=router(),
    )

    result = agent.run("get data from customer graph, fraud graph and sqlite db for C1001")

    assert result.success is True
    assert len(manager.calls) == 2
    assert manager.calls[0].input["graph_requests"][0]["graph_name"] == "customer_graph"
    assert manager.calls[0].input["graph_requests"][1]["graph_name"] == "fraud_graph"
    assert manager.calls[1].input["source"] == "business_db"


def test_authorization_questions_use_current_actor_not_conversation():
    agent = Agent(
        execution_manager=RecordingExecutionManager(),
        planner=FailingPlanner(),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=StaticSynthesizer(),
        policy=ActorPolicy(),
        resource_router=router(),
    )

    investigator = agent.run(
        "am I allowed to access customer_graph and fraud_graph?",
        session_id="authorization-session",
        user_id="investigator",
    )
    support_user = agent.run(
        "am I allowed to access customer_graph and fraud_graph?",
        session_id="authorization-session",
        user_id="support_user",
    )
    no_resource = agent.run(
        "am I allowed to see this?",
        session_id="authorization-session",
        user_id="support_user",
    )

    assert investigator.output == "customer_graph -> ALLOWED\nfraud_graph -> ALLOWED"
    assert support_user.output == "customer_graph -> ALLOWED\nfraud_graph -> DENIED"
    assert support_user.success is False
    assert "did not identify" in no_resource.error


def test_generic_execution_denial_emits_failed_progress_without_resource_success():
    from core.policy.default import DefaultPolicy, PolicyDecision

    graph = InMemoryKnowledgeGraph()
    graph.name = "restricted_graph"
    graph.add_node("node-1", label="Node")
    registry = KnowledgeGraphRegistry()
    registry.register(graph)
    calls = []
    graph.get_neighbors = lambda *args, **kwargs: calls.append("executed")

    class DenyingPolicy(DefaultPolicy):
        def authorize_resource(
            self, actor, resource_type, resource_name, action, context=None
        ):
            return PolicyDecision(
                False,
                "access denied",
                "test_policy",
            )

    manager = ExecutionManager(
        knowledge_graph_registry=registry,
        policy=DenyingPolicy(),
    )
    events = []
    manager.progress_reporter = ProgressReporter(events.append)
    result = manager.execute(
        Task(
            id="restricted-read",
            description="Read restricted graph",
            input={
                "query": "Read relationships",
                "source": "restricted_graph",
                "operation": "get_neighbors",
                "params": {"node_id": "node-1"},
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="generic-denial", user_id="support_user"),
    )

    assert result.success is False
    assert result.metadata["authorization_denied"] is True
    assert calls == []
    assert any(
        event.event_type == "execution_progress"
        and event.status == "failed"
        for event in events
    )
    assert not any(
        event.resource == "restricted_graph" and event.status == "completed"
        for event in events
    )


def test_execution_policy_denial_is_marked_for_terminal_agent_handling():
    from core.policy.default import DefaultPolicy, PolicyDecision

    class DenyingPolicy(DefaultPolicy):
        def authorize_execution(self, task, context):
            return PolicyDecision(False, "execution denied", "test_policy")

    manager = ExecutionManager(policy=DenyingPolicy())
    events = []
    manager.progress_reporter = ProgressReporter(events.append)
    result = manager.execute(
        Task(
            id="denied-task",
            description="Run a task",
            input={"query": "not executed"},
            metadata={"capability": "model"},
        ),
        AgentContext(request_id="execution-denial", user_id="support_user"),
    )

    assert result.success is False
    assert result.metadata["authorization_denied"] is True
    assert any(
        event.event_type == "authorization_completed" and event.status == "denied"
        for event in events
    )
    assert any(
        event.event_type == "execution_progress" and event.status == "failed"
        for event in events
    )
