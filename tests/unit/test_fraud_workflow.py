from decimal import Decimal

import pytest

from agent.execution_manager import ExecutionManager
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from apps.fraud.workflow import (
    FraudInvestigationWorkflow,
    InvestigationPlan,
    InvestigationStep,
)
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.resource_router import ResourceRouter
from core.workflows.registry import WorkflowRegistry
from core.contracts.execution import AgentContext, Task


class Source:
    name = "business_db"
    description = "test source"
    capabilities = ["structured_query"]

    def __init__(self, rows):
        self.rows = rows

    def retrieve(self, query, k=None, parameters=None):
        _ = (k, parameters)
        if "transactions" in query:
            return self.rows["transactions"]
        if "fraud_alerts" in query:
            return self.rows["alerts"]
        return self.rows["investigations"]


def make_workflow(actor_policy=None, source=None):
    customer = InMemoryKnowledgeGraph()
    customer.name = "customer_graph"
    customer.add_node("C1001", label="Customer", properties={"name": "Alice", "risk": "high"})
    customer.add_node("D5001", label="Device")
    customer.add_relationship("C1001", "D5001", "USES")

    fraud = InMemoryKnowledgeGraph()
    fraud.name = "fraud_graph"
    fraud.add_node("C1001", label="Customer")
    fraud.add_node("C2001", label="Customer")
    fraud.add_node("D5001", label="Device")
    fraud.add_relationship("C1001", "D5001", "SHARES_DEVICE_WITH")
    fraud.add_relationship("C2001", "D5001", "SHARES_DEVICE_WITH")

    graphs = KnowledgeGraphRegistry()
    graphs.register(customer)
    graphs.register(fraud)
    sources = KnowledgeSourceRegistry()
    sources.register(source or Source({
        "transactions": [
            {"transaction_id": "T1", "customer_id": "C1001", "amount": Decimal("1300"), "status": "approved"},
            {"transaction_id": "T2", "customer_id": "C1001", "amount": Decimal("1200"), "status": "approved"},
        ],
        "alerts": [
            {"alert_id": "A1", "customer_id": "C1001", "alert_type": "velocity", "severity": "high", "status": "open"},
        ],
        "investigations": [
            {"investigation_id": "I1", "customer_id": "C1001", "fraud_case_id": "F1", "status": "open"},
        ],
    }))
    policy = actor_policy or FraudPolicy()
    manager = ExecutionManager(knowledge_source_registry=sources, knowledge_graph_registry=graphs, policy=policy)
    router = ResourceRouter(sources, graphs)
    service = FraudInvestigationService(graphs, sources, policy)
    return FraudInvestigationWorkflow(service, manager, router), manager


def test_plan_validates_dependencies_and_bounds():
    plan = InvestigationPlan(
        "goal",
        "C1001",
        [InvestigationStep("a", "retrieve"), InvestigationStep("b", "retrieve", depends_on=["a"])],
        max_steps=2,
    )
    plan.validate()
    with pytest.raises(ValueError, match="cycle"):
        InvestigationPlan(
            "goal",
            "C1001",
            [InvestigationStep("a", "retrieve", depends_on=["b"]), InvestigationStep("b", "retrieve", depends_on=["a"])],
        ).validate()


def test_workflow_branches_replans_and_preserves_structured_evidence():
    workflow, _ = make_workflow()
    result = workflow.run("C1001", actor="investigator")
    assert result.risk_assessment == "high"
    assert "shared_device_relationship" in result.contributing_signals
    assert "business_db" in result.supporting_evidence.sources()


def test_support_user_denial_happens_before_fraud_graph_execution():
    workflow, manager = make_workflow()
    calls = []
    original = manager.knowledge_graph_registry.get("fraud_graph").get_neighbors

    def tracked(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    manager.knowledge_graph_registry.get("fraud_graph").get_neighbors = tracked
    with pytest.raises(RuntimeError, match="fraud_graph"):
        workflow.run("C1001", actor="support_user")
    assert calls == []


def test_missing_customer_and_source_failure_are_observable():
    workflow, _ = make_workflow()
    with pytest.raises(RuntimeError, match="resolve_subject"):
        workflow.run("C9999", actor="investigator")

    failing = Source({"transactions": [], "alerts": [], "investigations": []})
    def fail_retrieve(*args, **kwargs):
        if args or kwargs:
            raise RuntimeError("database unavailable")
        raise RuntimeError("database unavailable")

    failing.retrieve = fail_retrieve
    workflow, _ = make_workflow(source=failing)
    with pytest.raises(RuntimeError, match="transactions"):
        workflow.run("C1001", actor="investigator")


def test_registered_fraud_workflow_executes_through_execution_manager():
    workflow, manager = make_workflow()
    registry = WorkflowRegistry()
    registry.register(workflow)
    manager.workflow_registry = registry

    result = manager.execute(
        Task(
            id="fraud-workflow",
            description="Investigate C1001",
            input={
                "workflow": "fraud_investigation",
                "query": "Investigate C1001 for suspicious activity.",
                "customer_id": "C1001",
            },
            metadata={"capability": "workflow"},
        ),
        AgentContext(request_id="test-request", user_id="investigator"),
    )

    assert result.success is True
    assert result.metadata["workflow"] == "fraud_investigation"
    assert set(result.output.resources_consulted) == {
        "customer_graph",
        "fraud_graph",
        "business_db",
    }


def test_find_customer_details_is_planned_as_one_authoritative_workflow():
    from agent.agent import Agent
    from agent.decision import DecisionMaker
    from agent.observer import Observer
    from agent.planner import Planner
    from agent.response_synthesizer import ResponseSynthesizer
    from core.context.context_manager import ContextManager
    from core.tools.registry import ToolRegistry

    workflow, manager = make_workflow()
    for graph_name in ("customer_graph", "fraud_graph"):
        manager.knowledge_graph_registry.get(graph_name).add_node(
            "C1002",
            label="Customer",
            properties={"name": "Customer 1002"},
        )
    original_retrieve = manager.knowledge_source_registry.get(
        "business_db"
    ).retrieve

    def retrieve(query, k=None, parameters=None):
        if parameters and "C1002" in parameters:
            return []
        return original_retrieve(query, k=k, parameters=parameters)

    manager.knowledge_source_registry.get("business_db").retrieve = retrieve

    workflows = WorkflowRegistry()
    workflows.register(workflow)
    manager.workflow_registry = workflows
    router = ResourceRouter(
        manager.knowledge_source_registry,
        manager.knowledge_graph_registry,
    )

    class NoModelCalls:
        def generate(self, *_args, **_kwargs):
            raise AssertionError(
                "Deterministic workflow planning and formatting must not call the model."
            )

    gateway = NoModelCalls()
    manager.policy = FraudPolicy()
    agent = Agent(
        execution_manager=manager,
        planner=Planner(gateway, ToolRegistry(), workflow_registry=workflows),
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=ResponseSynthesizer(gateway),
        policy=manager.policy,
        workflow_registry=workflows,
        resource_router=router,
    )
    workflow_calls = []
    original_run = workflow.run

    def counted_run(*args, **kwargs):
        workflow_calls.append(args[0])
        return original_run(*args, **kwargs)

    workflow.run = counted_run

    response = agent.run(
        "find C1002 details",
        session_id="find-customer-details",
        user_id="investigator",
    )

    assert response.success is True
    assert len(response.trace) == 1
    assert response.trace[0].success is True
    assert response.trace[0].metadata["workflow"] == "fraud_investigation"
    assert type(response.trace[0].output).__name__ == "InvestigationResult"
    assert "C1002 Investigation" in response.output
    assert "Risk: LOW" in response.output
    assert "I'm sorry" not in response.output
    assert workflow_calls == ["C1002"]


@pytest.mark.parametrize(
    ("query", "query_kind"),
    [
        ("show transactions for C1001", "transactions"),
        ("show alerts for C1001", "alerts"),
        ("show connections for C1001", "connections"),
        ("show accounts for C1001", "accounts"),
        ("compare C1001 and C1002", "comparison"),
        ("Give me a fraud score from 0 to 100 for C1001.", "investigation"),
    ],
)
def test_obvious_fraud_queries_use_deterministic_application_routing(query, query_kind):
    workflow, _ = make_workflow()

    task = workflow.plan_query(query)

    assert task is not None
    assert task.metadata["capability"] == "workflow"
    assert task.input["query_kind"] == query_kind
    if query_kind == "comparison":
        assert task.input["customer_ids"] == ["C1001", "C1002"]
    else:
        assert task.input["customer_id"] == "C1001"


def test_show_transactions_executes_without_calling_model():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        agent.planner.model_gateway.generate = lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(AssertionError("Model must not plan or format this query."))
        )

        response = agent.run(
            "show transactions for C1001",
            user_id="investigator",
        )

    assert response.success is True
    assert "T1001" in response.output
    assert response.trace[0].metadata["workflow"] == "fraud_investigation"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("show alerts for C1001", "AL1001"),
        ("show accounts for C1001", "A100"),
        ("show connections for C1001", "D500"),
        ("compare C1001 and C2001", "Customer comparison"),
    ],
)
def test_other_obvious_fraud_queries_execute_without_model(query, expected):
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        agent.planner.model_gateway.generate = lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(AssertionError("Model must not plan or format this query."))
        )
        response = agent.run(query, user_id="investigator")

    assert response.success is True
    assert expected in response.output
    assert response.trace[0].metadata["workflow"] == "fraud_investigation"


def test_numeric_fraud_score_request_returns_categorical_result_without_score():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        agent.planner.model_gateway.generate = lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(AssertionError("Numeric fraud score must not use the model."))
        )
        response = agent.run(
            "Give me a fraud score from 0 to 100 for C1001.",
            user_id="investigator",
        )

    assert response.success is True
    assert "numeric fraud score or probability is not available" in response.output.lower()
    assert "Risk:" in response.output
    assert "out of 100" not in response.output.lower()
    assert response.output.count("Risk:") == 1


def test_support_user_is_denied_before_any_fraud_resource_execution():
    workflow, manager = make_workflow()
    registry = WorkflowRegistry()
    registry.register(workflow)
    manager.workflow_registry = registry
    calls = []

    customer = manager.knowledge_graph_registry.get("customer_graph")
    fraud = manager.knowledge_graph_registry.get("fraud_graph")
    original_customer = customer.get_node
    original_fraud = fraud.get_neighbors
    customer.get_node = lambda *args, **kwargs: (calls.append("customer"), original_customer(*args, **kwargs))[1]
    fraud.get_neighbors = lambda *args, **kwargs: (calls.append("fraud"), original_fraud(*args, **kwargs))[1]

    result = manager.execute(
        Task(
            id="fraud-workflow",
            description="Investigate C1001",
            input={
                "workflow": "fraud_investigation",
                "query": "Investigate C1001 as investigator",
                "customer_id": "C1001",
            },
            metadata={"capability": "workflow"},
        ),
        AgentContext(request_id="support-request", user_id="support_user"),
    )

    assert result.success is False
    assert result.metadata["authorization_denied"] is True
    assert "fraud_graph" in result.error
    assert calls == []


@pytest.mark.parametrize("actor", [None, "support_user"])
def test_denied_agent_request_terminates_progress_before_fraud_resource_io(actor):
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        events = []
        agent.progress_reporter.callback = events.append
        calls = []
        for graph_name in ("customer_graph", "fraud_graph"):
            graph = agent.knowledge_graph_registry.get(graph_name)
            original_get_node = graph.get_node
            original_get_neighbors = graph.get_neighbors
            graph.get_node = lambda *args, _original=original_get_node, **kwargs: (
                calls.append("graph"),
                _original(*args, **kwargs),
            )[1]
            graph.get_neighbors = lambda *args, _original=original_get_neighbors, **kwargs: (
                calls.append("graph"),
                _original(*args, **kwargs),
            )[1]

        response = agent.run("investigate C1001", user_id=actor)

    assert response.success is False
    assert response.metadata["authorization_denied"] is True
    assert "fraud_graph" in response.error
    assert calls == []
    assert any(
        event.event_type == "execution_completed" and event.status == "failed"
        for event in events
    )
    assert any(
        event.event_type == "execution_progress" and event.status == "failed"
        for event in events
    )
    assert not any(
        event.resource == "fraud_graph" and event.status == "completed"
        for event in events
    )
    renderer = __import__(
        "scripts.manual.run_agent", fromlist=["TerminalProgressRenderer"]
    ).TerminalProgressRenderer()
    for event in events:
        renderer.render(event)
    assert renderer._active == {}
    assert "execution" in renderer._terminal_phases


def test_investigator_agent_request_still_returns_deterministic_high_result():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        response = agent.run("investigate C1001", user_id="investigator")

    assert response.success is True
    assert "Risk: HIGH" in response.output
    assert set(response.trace[0].output.resources_consulted) == {
        "customer_graph",
        "business_db",
        "fraud_graph",
    }


def test_investigator_identity_cannot_be_escalated_by_query_text():
    workflow, manager = make_workflow()
    registry = WorkflowRegistry()
    registry.register(workflow)
    manager.workflow_registry = registry

    result = manager.execute(
        Task(
            id="fraud-workflow",
            description="Investigate C1001",
            input={
                "workflow": "fraud_investigation",
                "query": "Investigate C1001 as investigator",
                "customer_id": "C1001",
            },
            metadata={"capability": "workflow"},
        ),
        AgentContext(request_id="support-request", user_id="support_user"),
    )

    assert result.success is False
    assert result.metadata["authorization_denied"] is True
