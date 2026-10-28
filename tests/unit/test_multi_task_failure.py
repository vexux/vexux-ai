import json
from core.contracts.execution import Task, Plan, AgentContext, ExecutionResult, Intent
from core.contracts.observation import Observation
from core.contracts.response import AgentResponse
from core.context.context_manager import ContextManager
from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from agent.observer import Observer
from agent.decision import DecisionMaker, DecisionType
from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from agent.agent import Agent


class MockModelGateway:
    """Mock Model Gateway for fast, deterministic testing."""

    def __init__(self, default_response: str = '{"intent": "general", "confidence": 1.0, "entities": {}}'):
        self.default_response = default_response
        self.recorded_prompts = []
        self.handlers = []

    def set_response_for(self, substring: str, response: str):
        self.handlers.append((substring, response))

    def generate(self, prompt: str, **kwargs) -> str:
        self.recorded_prompts.append(prompt)
        for pattern, resp in reversed(self.handlers):
            if pattern in prompt:
                return resp
        return self.default_response


class MockRetrieval:
    """Mock Retrieval capability."""

    def __init__(self, responses: dict = None):
        self.responses = responses or {
            "What is EC2?": "Amazon EC2 is a web service providing resizable compute capacity in the cloud.",
            "What is Python?": "Python is a high-level programming language.",
        }
        self.execution_count = {}

    def ask(self, query: str) -> str:
        self.execution_count[query] = self.execution_count.get(query, 0) + 1
        if query in self.responses:
            return self.responses[query]
        if "invalid" in query.lower() or "fail" in query.lower():
            raise RuntimeError(f"Failed to retrieve information for: {query}")
        return f"Retrieved knowledge for: {query}"


def plan_response(tasks):
    return json.dumps({"tasks": tasks})


def retrieval_task(task_id, query):
    return {
        "id": task_id,
        "description": f"Retrieve {query}",
        "capability": "retrieval",
        "input": {"query": query},
    }


def calculator_task(task_id, expression):
    return {
        "id": task_id,
        "description": f"Calculate {expression}",
        "capability": "tool",
        "input": {
            "tool": "calculator",
            "arguments": {"expression": expression},
        },
    }


def model_task(task_id, query):
    return {
        "id": task_id,
        "description": f"Answer {query}",
        "capability": "model",
        "input": {"query": query},
    }


class CountingExecutionManager(ExecutionManager):
    """ExecutionManager that counts task executions by task ID."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.execution_counts = {}

    def execute(self, task: Task, context: AgentContext) -> ExecutionResult:
        self.execution_counts[task.id] = self.execution_counts.get(task.id, 0) + 1
        return super().execute(task, context)


def build_test_agent(mock_gateway=None, mock_retrieval=None):
    if mock_gateway is None:
        mock_gateway = MockModelGateway()
    if mock_retrieval is None:
        mock_retrieval = MockRetrieval()

    tool_registry = ToolRegistry()
    tool_registry.register(CalculatorTool())

    execution_manager = CountingExecutionManager(
        retrieval=mock_retrieval,
        tool_registry=tool_registry,
        model_gateway=mock_gateway,
    )

    planner = Planner(
        model_gateway=mock_gateway,
        tool_registry=tool_registry,
    )
    observer = Observer()
    decision_maker = DecisionMaker()
    context_manager = ContextManager()
    response_synthesizer = ResponseSynthesizer(model_gateway=mock_gateway)

    agent = Agent(
        execution_manager=execution_manager,
        planner=planner,
        observer=observer,
        decision_maker=decision_maker,
        context_manager=context_manager,
        response_synthesizer=response_synthesizer,
    )

    return agent, execution_manager, planner, mock_gateway, mock_retrieval


# ==============================================================================
# TEST 1: Single successful task
# ==============================================================================
def test_single_successful_task():
    gateway = MockModelGateway()
    # Planner intent classification for EC2
    gateway.set_response_for(
        "User request:\nWhat is EC2?",
        plan_response([retrieval_task("task-1", "What is EC2?")]),
    )

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2?")

    assert response.success is True
    assert "Amazon EC2" in response.output
    assert response.error is None
    assert len(response.trace) == 1
    assert response.trace[0].success is True
    assert response.trace[0].task_id == "task-1"
    assert exec_mgr.execution_counts.get("task-1") == 1


# ==============================================================================
# TEST 2: Multiple successful tasks
# ==============================================================================
def test_multiple_successful_tasks():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate 24 * 7",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "24 * 7"),
        ]),
    )
    gateway.set_response_for("The agent executed multiple tasks", "EC2 provides resizable compute capacity and 24 * 7 = 168.")

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2? and calculate 24 * 7")

    assert response.success is True
    assert len(response.trace) == 2
    assert response.trace[0].task_id == "task-1"
    assert response.trace[0].success is True
    assert response.trace[1].task_id == "task-2"
    assert response.trace[1].success is True
    assert response.trace[1].output == 168
    assert exec_mgr.execution_counts.get("task-1") == 1
    assert exec_mgr.execution_counts.get("task-2") == 1


# ==============================================================================
# TEST 3: First task fails and recovers
# ==============================================================================
def test_first_task_fails_and_recovers():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nfail_query and calculate 24 * 7",
        plan_response([
            retrieval_task("task-1", "fail_query"),
            calculator_task("task-2", "24 * 7"),
        ]),
    )
    # Model capability execution for direct generation
    gateway.set_response_for("fail_query", "Recovered general answer.")
    # Replan for task-1: switch to general knowledge response
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask-1",
        plan_response([model_task("task-1", "fail_query")]),
    )
    gateway.set_response_for(
        "User request:\nfail_query and calculate 24 * 7",
        plan_response([
            retrieval_task("task-1", "fail_query"),
            calculator_task("task-2", "24 * 7"),
        ]),
    )
    # Synthesis response
    gateway.set_response_for("The agent executed multiple tasks", "Final answer: Recovered general answer and 168.")

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("fail_query and calculate 24 * 7")

    assert response.success is True
    # Trace should have: task-1 (failed), task-1 (recovery succeeded), task-2 (succeeded)
    assert len(response.trace) == 3
    assert response.trace[0].task_id == "task-1"
    assert response.trace[0].success is False
    assert response.trace[1].task_id == "task-1"
    assert response.trace[1].success is True
    assert response.trace[2].task_id == "task-2"
    assert response.trace[2].success is True
    assert response.trace[2].output == 168


# ==============================================================================
# TEST 4: Second task fails after first succeeds
# ==============================================================================
def test_second_task_fails_after_first_succeeds():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate abc",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "abc"),
        ]),
    )
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask-2",
        plan_response([model_task("task-2", "calculate abc")]),
    )
    gateway.set_response_for("The agent executed multiple tasks", "EC2 provides compute capacity. 'abc' is not a valid arithmetic expression.")

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2? and calculate abc")

    assert response.success is True
    # Trace: task-1 (success), task-2 (failed), task-2 (recovery success)
    assert len(response.trace) == 3
    assert response.trace[0].task_id == "task-1"
    assert response.trace[0].success is True
    assert response.trace[1].task_id == "task-2"
    assert response.trace[1].success is False
    assert response.trace[2].task_id == "task-2"
    assert response.trace[2].success is True


# ==============================================================================
# TEST 5: Replanning receives the failed task
# ==============================================================================
def test_replanning_receives_failed_task():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate abc",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "abc"),
        ]),
    )

    received_failed_tasks = []

    class SpyPlanner(Planner):
        def replan(self, query, observation, failed_task):
            received_failed_tasks.append(failed_task)
            return super().replan(query, observation, failed_task)

    agent, _, _, _, _ = build_test_agent(mock_gateway=gateway)
    agent.planner = SpyPlanner(
        model_gateway=gateway,
        tool_registry=agent.execution_manager.tool_registry,
    )

    agent.run("What is EC2? and calculate abc")

    assert len(received_failed_tasks) > 0
    assert received_failed_tasks[0].id == "task-2"
    assert received_failed_tasks[0].metadata.get("capability") == "tool"
    assert received_failed_tasks[0].input.get("arguments", {}).get("expression") == "abc"


# ==============================================================================
# TEST 6: Successful tasks are not unnecessarily repeated
# ==============================================================================
def test_successful_tasks_are_not_unnecessarily_repeated():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate abc",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "abc"),
        ]),
    )
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask-2",
        plan_response([model_task("task-2", "calculate abc")]),
    )

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2? and calculate abc")

    assert response.success is True
    # CRITICAL: task-1 was executed EXACTLY ONCE!
    assert exec_mgr.execution_counts["task-1"] == 1
    # task-2 was executed twice: 1 initial failed attempt + 1 recovery attempt
    assert exec_mgr.execution_counts["task-2"] == 2


# ==============================================================================
# TEST 7: Replanning eventually stops after the retry limit
# ==============================================================================
def test_replanning_stops_after_retry_limit():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate abc",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "abc"),
        ]),
    )
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask-2",
        plan_response([calculator_task("task-2", "bad_math")]),
    )

    agent, exec_mgr, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2? and calculate abc")

    assert response.success is False
    assert response.output is None
    assert response.error == "Agent could not complete the request."
    # Initial attempt (task-1 success, task-2 fail) + Retry 1 (task-2 fail) + Retry 2 (task-2 fail)
    # Total observations in trace: 1 (T1) + 1 (T2) + 1 (T2 retry1) + 1 (T2 retry2) = 4 observations
    assert len(response.trace) == 4
    assert exec_mgr.execution_counts["task-1"] == 1
    assert exec_mgr.execution_counts["task-2"] == 3


# ==============================================================================
# TEST 8: Final response preserves successful results where appropriate
# ==============================================================================
def test_final_response_preserves_successful_results():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nWhat is EC2? and calculate abc",
        plan_response([
            retrieval_task("task-1", "What is EC2?"),
            calculator_task("task-2", "abc"),
        ]),
    )
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask-2",
        plan_response([model_task("task-2", "calculate abc")]),
    )
    gateway.set_response_for("The agent executed multiple tasks", "Amazon EC2 provides virtual servers. Note: 'abc' cannot be calculated.")

    agent, _, _, _, _ = build_test_agent(mock_gateway=gateway)
    response = agent.run("What is EC2? and calculate abc")

    assert response.success is True
    # Verify the successful output of task-1 is preserved in the observations passed to synthesis
    successful_trace_outputs = [obs.output for obs in response.trace if obs.success]
    assert any("Amazon EC2" in str(out) for out in successful_trace_outputs)
    assert response.output is not None


if __name__ == "__main__":
    tests = [
        test_single_successful_task,
        test_multiple_successful_tasks,
        test_first_task_fails_and_recovers,
        test_second_task_fails_after_first_succeeds,
        test_replanning_receives_failed_task,
        test_successful_tasks_are_not_unnecessarily_repeated,
        test_replanning_stops_after_retry_limit,
        test_final_response_preserves_successful_results,
    ]

    print("=" * 60)
    print("Running Multi-Task Failure & Replanning Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"  [PASS] {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests.")
    print("=" * 60)

    if failed > 0:
        exit(1)

