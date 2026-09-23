from apps.fraud.demo import create_demo_agent
from apps.fraud.domain import Customer, InvestigationResult
from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.observer import Observer
from core.context.context_manager import ContextManager
from core.contracts.evidence import EvidenceSet
from core.contracts.execution import ExecutionResult, Plan, Task
from core.contracts.workflow import WorkflowExecutionError


class _Planner:
    def __init__(self):
        self.replans = 0

    def create_plan(self, query, **kwargs):
        return Plan(tasks=[Task(
            id="terminal-task",
            description=query,
            input={},
            metadata={"capability": "workflow"},
        )])

    def replan(self, *args, **kwargs):
        self.replans += 1
        raise AssertionError("terminal workflow must not be replanned")


class _TerminalWorkflowManager:
    def execute(self, task, context):
        return ExecutionResult(
            success=False,
            error="Authoritative workflow failure",
            metadata={
                "terminal": True,
                "retryable": False,
                "authoritative": True,
                "failure_category": "infrastructure",
            },
        )


class _Synthesizer:
    def synthesize(self, *args, **kwargs):
        raise AssertionError("terminal workflow must not be synthesized")


def _result() -> InvestigationResult:
    return InvestigationResult(
        subject=Customer("C1001", "Alice Smith", "high"),
        findings=[
            "2 open high-severity fraud alerts are associated with the customer.",
            "Transaction activity exceeds the deterministic investigation threshold.",
            "The customer is connected to another customer through a shared device.",
            "An investigation record is associated with the customer.",
        ],
        risk_assessment="high",
        supporting_evidence=EvidenceSet(),
        resources_consulted=["customer_graph", "fraud_graph", "business_db"],
    )


def test_investigation_result_has_deterministic_human_readable_text():
    text = _result().to_user_text()

    assert "C1001 Investigation" in text
    assert "Risk: HIGH" in text
    assert text.count("- ") == 4
    assert "Resources consulted:\ncustomer_graph, fraud_graph, business_db" in text
    for finding in _result().findings:
        assert finding in text


def test_one_line_investigation_result_is_concise_and_deterministic():
    text = _result().to_user_text(one_line=True)

    assert "\n" not in text
    assert "C1001 Investigation: HIGH;" in text
    assert "Resources: customer_graph, fraud_graph, business_db" in text


def test_unavailable_fraud_resource_is_terminal_and_not_model_synthesized(monkeypatch):
    with create_demo_agent() as agent:
        workflow = agent.workflow_registry.get("fraud_investigation")

        def fail_workflow(*args, **kwargs):
            raise RuntimeError("Neo4j connection refused")

        workflow.run = fail_workflow
        monkeypatch.setattr(
            agent.planner.model_gateway,
            "generate",
            lambda *args, **kwargs: "The score is 0.6280381679534912.",
        )

        response = agent.run("Investigate C1001", session_id="fraud-failure")

    assert response.success is False
    assert response.output is None
    assert response.error == (
        "Fraud investigation could not be completed because "
        "the required fraud data source is unavailable."
    )
    assert "0.6280381679534912" not in str(response.output)
    assert response.metadata["terminal"] is True
    assert response.metadata["authoritative"] is True
    assert response.metadata["failure_category"] == "infrastructure"


def test_generic_terminal_workflow_failure_is_not_replanned():
    planner = _Planner()
    agent = Agent(
        execution_manager=_TerminalWorkflowManager(),
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=_Synthesizer(),
    )

    response = agent.run("run terminal workflow")

    assert response.success is False
    assert response.error == "Authoritative workflow failure"
    assert response.metadata["terminal"] is True
    assert response.metadata["authoritative"] is True
    assert planner.replans == 0


def test_execution_manager_preserves_generic_workflow_failure_contract():
    class GenericWorkflow:
        name = "generic_terminal_workflow"
        description = "generic terminal workflow"
        input_schema = {"type": "object"}

        def execute(self, workflow_input, context):
            raise WorkflowExecutionError(
                "generic infrastructure failure",
                terminal=True,
                retryable=False,
                authoritative=True,
                failure_category="infrastructure",
            )

    from core.contracts.execution import AgentContext
    from core.workflows.registry import WorkflowRegistry
    from agent.execution_manager import ExecutionManager

    registry = WorkflowRegistry()
    registry.register(GenericWorkflow())
    result = ExecutionManager(workflow_registry=registry).execute(
        Task(
            id="generic-task",
            description="generic workflow",
            input={"workflow": "generic_terminal_workflow"},
            metadata={"capability": "workflow"},
        ),
        AgentContext(request_id="generic-request"),
    )

    assert result.success is False
    assert result.metadata["terminal"] is True
    assert result.metadata["authoritative"] is True
    assert result.metadata["failure_category"] == "infrastructure"
