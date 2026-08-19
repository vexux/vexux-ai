import json

from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager
from core.contracts.execution import ExecutionResult
from core.contracts.observation import Observation
from core.tools.registry import ToolRegistry


class Gateway:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else "generated response"


def plan(query):
    return json.dumps({
        "tasks": [{
            "id": "task-1",
            "description": "Answer request",
            "capability": "model",
            "input": {"query": query},
        }]
    })


def build_agent(gateway, context_manager=None):
    context_manager = context_manager or ContextManager()
    planner = Planner(gateway, ToolRegistry())
    return Agent(
        execution_manager=ExecutionManager(model_gateway=gateway),
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=context_manager,
        response_synthesizer=ResponseSynthesizer(gateway),
    )


def test_new_session_creates_state():
    manager = ContextManager()

    context = manager.create("request-1", session_id="session-a")

    assert context.session_id == "session-a"
    assert context.conversation_history == []
    assert "session-a" in manager._sessions


def test_same_session_accesses_previous_conversation_context():
    manager = ContextManager()
    first = manager.create("request-1", session_id="session-a")
    manager.add_conversation_turn(first, "What is EC2?", "EC2 is compute.")

    second = manager.create("request-2", session_id="session-a")

    assert second.conversation_history == [{
        "query": "What is EC2?",
        "response": "EC2 is compute.",
    }]


def test_different_sessions_are_isolated():
    manager = ContextManager()
    first = manager.create("request-1", session_id="session-a")
    manager.add_conversation_turn(first, "What is EC2?", "EC2 is compute.")

    other = manager.create("request-2", session_id="session-b")

    assert other.conversation_history == []


def test_request_ids_remain_distinct_within_session():
    manager = ContextManager()

    first = manager.create("request-1", session_id="session-a")
    second = manager.create("request-2", session_id="session-a")

    assert first.request_id != second.request_id
    assert first.session_id == second.session_id


def test_requests_without_session_id_still_work_without_shared_state():
    manager = ContextManager()
    first = manager.create("request-1")
    manager.add_conversation_turn(first, "hello", "hi")
    second = manager.create("request-2")

    assert first.session_id is None
    assert second.session_id is None
    assert second.conversation_history == []
    assert manager._sessions == {}


def test_history_is_bounded():
    manager = ContextManager(history_limit=2)
    context = manager.create("request-1", session_id="session-a")

    for index in range(3):
        manager.add_conversation_turn(context, f"q{index}", f"a{index}")

    latest = manager.create("request-4", session_id="session-a")

    assert [turn["query"] for turn in latest.conversation_history] == ["q1", "q2"]


def test_planner_receives_previous_conversation_context():
    gateway = Gateway([plan("What about its pricing?")])
    manager = ContextManager()
    context = manager.create("request-1", session_id="session-a")
    manager.add_conversation_turn(context, "What is EC2?", "EC2 is compute.")
    planner = Planner(gateway, ToolRegistry())

    planner.create_plan(
        "What about its pricing?",
        conversation_context=manager.create("request-2", session_id="session-a").conversation_history,
    )

    assert "What is EC2?" in gateway.prompts[0]
    assert "EC2 is compute." in gateway.prompts[0]


def test_synthesizer_receives_previous_conversation_context():
    gateway = Gateway(["final answer"])
    synthesizer = ResponseSynthesizer(gateway)

    result = synthesizer.synthesize(
        "What about its pricing?",
        [Observation(
            success=True,
            output="pricing result",
            summary="completed",
        )],
        conversation_context=[{
            "query": "What is EC2?",
            "response": "EC2 is compute.",
        }],
    )

    assert result == "final answer"
    assert "What is EC2?" in gateway.prompts[0]
    assert "EC2 is compute." in gateway.prompts[0]


def test_agent_stores_and_reuses_session_context():
    gateway = Gateway([
        plan("What is EC2?"),
        "EC2 is compute.",
        plan("What about its pricing?"),
        "EC2 pricing depends on usage.",
        "Second final answer.",
    ])
    manager = ContextManager()
    agent = build_agent(gateway, manager)

    first = agent.run("What is EC2?", session_id="session-a")
    second = agent.run("What about its pricing?", session_id="session-a")

    assert first.success is True
    assert second.success is True
    assert second.output == "Second final answer."
    assert "What is EC2?" in gateway.prompts[2]
    assert "EC2 is compute." in gateway.prompts[2]
