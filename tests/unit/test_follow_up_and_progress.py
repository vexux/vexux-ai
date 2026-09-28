import json

from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager
from core.context.follow_up import interpret_follow_up
from core.contracts.execution import ExecutionResult, Task
from core.contracts.observation import Observation
from core.contracts.progress import ProgressEvent, ProgressReporter
from core.policy.default import DefaultPolicy
from core.tools.registry import ToolRegistry
from core.workflows.registry import WorkflowRegistry


class _Gateway:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return "A response based on the supplied context."


class _FormattedResult:
    def to_user_text(self, one_line=False):
        return "Deterministic result with its complete findings."


class _QueryWorkflow:
    name = "reference_workflow"
    description = "A generic test workflow."
    input_schema = {"type": "object"}

    def __init__(self):
        self.planning_queries = []

    def plan_query(self, query):
        self.planning_queries.append(query)
        if "review item" not in query.lower():
            return None
        return Task(
            id="workflow-task",
            description="Run the registered workflow",
            input={"workflow": self.name, "query": query},
            metadata={"capability": "workflow"},
        )

    def execute(self, workflow_input, context):
        return _FormattedResult()


class _RecordingExecutionManager:
    def execute(self, task, context):
        return ExecutionResult(success=True, output=_FormattedResult())


class _RecordingSynthesizer:
    def __init__(self):
        self.contexts = []

    def synthesize(self, query, observations, conversation_context=None):
        self.contexts.append(list(conversation_context or []))
        output = next(item.output for item in observations if item.success)
        formatter = getattr(output, "to_user_text", None)
        return formatter() if callable(formatter) else str(output)


def _agent(
    *,
    gateway,
    context_manager=None,
    workflow_registry=None,
    events=None,
    execution_manager=None,
):
    planner = Planner(
        gateway,
        ToolRegistry(),
        workflow_registry=workflow_registry,
    )
    synthesizer = _RecordingSynthesizer()
    agent = Agent(
        execution_manager=execution_manager or _RecordingExecutionManager(),
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=context_manager or ContextManager(),
        response_synthesizer=synthesizer,
        workflow_registry=workflow_registry,
        progress_callback=events.append if events is not None else None,
    )
    return agent, synthesizer


def test_follow_up_interpreter_requires_history_and_explicit_reference():
    history = [{"query": "review item 42", "response": "A result."}]

    assert interpret_follow_up("in detail", None) is None
    assert interpret_follow_up("maybe", history) is None
    interpreted = interpret_follow_up("in detail", history)

    assert interpreted is not None
    assert interpreted.previous_turn == history[0]
    assert interpreted.kind == "expand"
    assert interpreted.base_query == "review item 42"
    assert interpreted.planning_query == "review item 42\nFollow-up request: in detail"


def test_response_synthesizer_uses_generic_follow_up_formatter_protocol():
    class _FollowUpResult:
        def __init__(self):
            self.request = None

        def to_follow_up_text(self, *, kind, previous_response):
            self.request = (kind, previous_response)
            return "Expanded deterministic result."

    result = _FollowUpResult()
    synthesizer = ResponseSynthesizer(_Gateway())
    response = synthesizer.synthesize(
        "in detail",
        [Observation(success=True, output=result, summary="completed")],
        conversation_context=[{
            "query": "review item 42",
            "response": "Original result.",
        }],
    )

    assert response == "Expanded deterministic result."
    assert result.request == ("expand", "Original result.")


def test_follow_up_references_previous_result_and_remains_deterministic():
    gateway = _Gateway()
    context_manager = ContextManager()
    workflow = _QueryWorkflow()
    workflows = WorkflowRegistry()
    workflows.register(workflow)
    agent, synthesizer = _agent(
        gateway=gateway,
        context_manager=context_manager,
        workflow_registry=workflows,
    )

    first = agent.run("review item 42", session_id="follow-up")
    second = agent.run("in detail", session_id="follow-up")

    assert first.success and second.success
    assert second.output == "Deterministic result with its complete findings."
    assert workflow.planning_queries[-1] == (
        "review item 42\nFollow-up request: in detail"
    )
    assert synthesizer.contexts[-1] == [{
        "query": "review item 42",
        "response": "Deterministic result with its complete findings.",
    }]
    assert gateway.prompts == []


def test_fraud_workflow_follow_up_returns_more_deterministic_detail():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        initial = agent.run(
            "Investigate C1001",
            session_id="detailed-follow-up",
            user_id="investigator",
        )
        detail = agent.run(
            "in detail",
            session_id="detailed-follow-up",
            user_id="investigator",
        )

    assert initial.success and detail.success
    assert detail.output != initial.output
    assert "Additional detail:" in detail.output
    assert "Transaction records reviewed: 1" in detail.output
    assert "Alert records reviewed: 1" in detail.output
    assert "Investigation records reviewed: 1" in detail.output
    assert "Open high-severity alerts" in detail.output
    assert "Risk: HIGH" in detail.output
    assert "Resources consulted:" in detail.output


def test_chained_follow_up_keeps_original_query_for_deterministic_summary():
    from apps.fraud.demo import create_demo_agent

    with create_demo_agent() as agent:
        first = agent.run(
            "Investigate C1001",
            session_id="chained-follow-up",
            user_id="investigator",
        )
        detail = agent.run(
            "in detail",
            session_id="chained-follow-up",
            user_id="investigator",
        )
        summary = agent.run(
            "summarize that",
            session_id="chained-follow-up",
            user_id="investigator",
        )

    assert first.success and detail.success and summary.success
    assert "Additional detail:" in detail.output
    assert "\n" not in summary.output
    assert "C1001 Investigation: HIGH;" in summary.output
    assert "Resources: customer_graph, business_db, fraud_graph" in summary.output


def test_independent_request_does_not_inherit_previous_context():
    gateway = _Gateway([
        json.dumps({
            "tasks": [{
                "id": "task-1",
                "description": "Retrieve information",
                "capability": "retrieval",
                "input": {"query": "What is EC2?"},
            }]
        }),
    ])
    context_manager = ContextManager()
    workflow = _QueryWorkflow()
    workflows = WorkflowRegistry()
    workflows.register(workflow)
    agent, synthesizer = _agent(
        gateway=gateway,
        context_manager=context_manager,
        workflow_registry=workflows,
    )

    agent.run("review item 42", session_id="independent")
    response = agent.run("What is EC2?", session_id="independent")

    assert response.success
    assert synthesizer.contexts[-1] == []
    assert workflow.planning_queries[-1] == "What is EC2?"


def test_follow_up_detection_supports_generic_reference_phrases():
    history = [{"query": "Compare the results", "response": "Two items."}]
    for query in (
        "explain that",
        "give me more information",
        "summarize that",
        "expand the previous result",
        "what about the second one?",
    ):
        assert interpret_follow_up(query, history) is not None


def test_progress_event_creation_contains_generic_metadata():
    seen = []
    reporter = ProgressReporter(seen.append)

    event = reporter.emit(
        "execution_progress",
        "execution",
        "Resource execution completed.",
        task_id="task-7",
        capability="retrieval",
        resource="registered_source",
        status="completed",
        duration_ms=12.5,
        metadata={"attempt": 1},
    )

    assert isinstance(event, ProgressEvent)
    assert seen == [event]
    assert event.event_type == "execution_progress"
    assert event.phase == "execution"
    assert event.task_id == "task-7"
    assert event.capability == "retrieval"
    assert event.resource == "registered_source"
    assert event.status == "completed"
    assert event.duration_ms == 12.5
    assert event.metadata == {"attempt": 1}
    assert event.timestamp.tzinfo is not None


def test_progress_callback_propagates_ordered_events_through_agent_loop():
    events = []
    gateway = _Gateway([
        json.dumps({
            "tasks": [{
                "id": "task-1",
                "description": "Answer request",
                "capability": "model",
                "input": {"query": "How are you?"},
            }]
        }),
        "I am ready.",
        "A clear final response.",
    ])
    agent, _ = _agent(
        gateway=gateway,
        events=events,
        execution_manager=ExecutionManager(
            model_gateway=gateway,
            policy=DefaultPolicy(),
        ),
    )

    response = agent.run("How are you?")

    assert response.success
    types = [event.event_type for event in events]
    expected = [
        "request_received",
        "planning_started",
        "planning_completed",
        "execution_started",
        "authorization_started",
        "authorization_completed",
        "execution_progress",
        "execution_completed",
        "observation_created",
        "decision_made",
        "response_started",
        "response_completed",
    ]
    positions = [types.index(event_type) for event_type in expected]
    assert positions == sorted(positions)
    execution_event = next(event for event in events if event.event_type == "execution_started")
    assert execution_event.task_id == "task-1"
    assert execution_event.capability == "model"
    assert response.metadata["timings_ms"]["planning"] >= 0
    assert response.metadata["timings_ms"]["execution"] >= 0
    assert response.metadata["timings_ms"]["total"] >= 0


def test_generic_terminal_failure_publishes_failure_event_without_domain_metadata():
    class _TerminalExecutor:
        def execute(self, task, context):
            return ExecutionResult(
                success=False,
                error="Authoritative workflow failure.",
                metadata={
                    "terminal": True,
                    "authoritative": True,
                    "failure_category": "infrastructure",
                },
            )

    events = []
    workflow = _QueryWorkflow()
    workflows = WorkflowRegistry()
    workflows.register(workflow)
    gateway = _Gateway()
    planner = Planner(gateway, ToolRegistry(), workflow_registry=workflows)
    agent = Agent(
        execution_manager=_TerminalExecutor(),
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=_RecordingSynthesizer(),
        workflow_registry=workflows,
        progress_callback=events.append,
    )

    response = agent.run("review item 42")

    assert response.success is False
    failed = next(event for event in events if event.event_type == "workflow_failed")
    assert failed.status == "failed"
    assert failed.metadata == {
        "authoritative": True,
        "failure_category": "infrastructure",
    }
    assert failed.resource is None
    assert not any("fraud" in key.lower() for key in failed.metadata)
