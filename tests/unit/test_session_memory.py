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


def test_agent_model_task_has_conversation_context():
    """Regression test: Model tasks should have access to previous conversation context.

    Turn 1: User says "My favorite language for this conversation is Python."
    Turn 2: User asks "What language did I just say?"

    Expected: The agent should answer "Python" because the model task should have
    access to the conversation history.

    This test verifies that the model task execution receives the conversation context.
    """
    gateway = Gateway([
        plan("My favorite language for this conversation is Python."),
        "Python is a great choice.",
        plan("What language did I just say?"),
        "Python",
        "You said Python.",
    ])
    manager = ContextManager()
    agent = build_agent(gateway, manager)

    # Turn 1: User states their favorite language
    first = agent.run(
        "My favorite language for this conversation is Python.",
        session_id="terminal-session"
    )
    assert first.success is True

    # Turn 2: User asks what language they said
    second = agent.run(
        "What language did I just say?",
        session_id="terminal-session"
    )
    assert second.success is True

    # Find the model task prompt for turn 2
    # We know turn 2 model task should reference previous conversation
    model_turn2_prompt = None
    for prompt in gateway.prompts:
        if "What language did I just say?" in prompt and \
           "You are producing the final response" not in prompt and \
           "structured planning" not in prompt.lower():
            # This should be the model task prompt for turn 2
            model_turn2_prompt = prompt
            break

    assert model_turn2_prompt is not None, "Could not find model task prompt for turn 2"

    # THE KEY TEST: The model task prompt should contain the previous conversation
    # This is the bug - model tasks don't receive conversation context
    assert "My favorite language" in model_turn2_prompt or \
           "Python is a great choice" in model_turn2_prompt, \
           f"Model task for turn 2 should have conversation context. Prompt: {model_turn2_prompt}"
