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
    result = workflow.run("C1001")
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
        workflow.run("C9999")

    failing = Source({"transactions": [], "alerts": [], "investigations": []})
    def fail_retrieve(*args, **kwargs):
        if args or kwargs:
            raise RuntimeError("database unavailable")
        raise RuntimeError("database unavailable")

    failing.retrieve = fail_retrieve
    workflow, _ = make_workflow(source=failing)
    with pytest.raises(RuntimeError, match="transactions"):
        workflow.run("C1001")


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
