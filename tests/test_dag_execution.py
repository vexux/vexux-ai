import pytest
from core.contracts.execution import Task, Plan, ExecutionResult
from agent.agent import Agent
from agent.planner import Planner
from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager


class FakePlanner:
    def __init__(self, plan: Plan):
        self._plan = plan

    def create_plan(self, query, conversation_context=None, intent=None, observation=None):
        return self._plan

    def replan(self, *args, **kwargs):
        # For simplicity, return the same plan (tests focus on scheduling)
        return self._plan


class FakeExecutionManager:
    def __init__(self, fail_tasks=None):
        self.fail_tasks = set(fail_tasks or [])
        self.calls = []

    def execute(self, task, context):
        self.calls.append(task.id)
        if task.id in self.fail_tasks:
            return ExecutionResult(success=False, error=f"Simulated failure: {task.id}")
        return ExecutionResult(success=True, output={"task_id": task.id})


class FakeResponseSynth:
    def synthesize(self, query, observations, conversation_context=None):
        return "synthesized"


def make_tasks(defs):
    # defs: list of tuples (id, capability, depends_on_list)
    tasks = []
    for tid, cap, deps in defs:
        tasks.append(Task(id=tid, description=f"task {tid}", input={}, metadata={"capability": cap}, depends_on=deps or []))
    return tasks


def test_linear_chain_execution_order():
    # A -> B -> C
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["B"])])
    plan = Plan(tasks=tasks)

    planner = FakePlanner(plan)
    exec_mgr = FakeExecutionManager()
    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth())

    resp = agent.run("q")
    # All tasks should have been executed in order A,B,C
    assert exec_mgr.calls[:3] == ["A", "B", "C"]
    # Observations should include three successful entries
    assert len(resp.trace) >= 3
    assert resp.success is True


def test_fan_out_deterministic_order():
    # A -> B and A -> C ; B defined before C in plan
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["A"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = FakeExecutionManager()
    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth())

    resp = agent.run("q")
    # After A, B and C become ready — they should execute in plan order B then C
    assert exec_mgr.calls[0] == "A"
    assert exec_mgr.calls[1:3] == ["B", "C"]
    assert resp.success is True


def test_fan_in_waits_for_all_predecessors():
    # A -> C ; B -> C ; C waits for both
    tasks = make_tasks([("A", "tool", []), ("B", "tool", []), ("C", "tool", ["A", "B"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = FakeExecutionManager()

    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth())

    resp = agent.run("q")
    # A and B should execute before C
    assert "C" in exec_mgr.calls
    idx_c = exec_mgr.calls.index("C")
    assert "A" in exec_mgr.calls and "B" in exec_mgr.calls
    assert exec_mgr.calls.index("A") < idx_c
    assert exec_mgr.calls.index("B") < idx_c
    assert resp.success is True


class FakeToolRegistry:
    def list_tools(self):
        return ["calculator"]

    def get(self, name):
        return type("T", (), {"input_schema": {"required": [], "properties": {}}})()


def test_unknown_dependency_rejected_by_planner():
    p = Planner(model_gateway=None, tool_registry=FakeToolRegistry())
    # craft JSON response with task C depending on unknown 'X'
    response = '{"tasks":[{"id":"A","description":"a","capability":"tool","input":{"tool":"calculator","arguments":{} }},{"id":"C","description":"c","capability":"tool","input":{"tool":"calculator","arguments":{}}, "depends_on":["X"]}] }'
    with pytest.raises(ValueError):
        p._parse_plan(response)


def test_cycle_rejected_by_planner():
    p = Planner(model_gateway=None, tool_registry=FakeToolRegistry())
    response = '{"tasks":[{"id":"A","description":"a","capability":"tool","input":{"tool":"calculator","arguments":{}}, "depends_on":["C"]},{"id":"B","description":"b","capability":"tool","input":{"tool":"calculator","arguments":{}}, "depends_on":["A"]},{"id":"C","description":"c","capability":"tool","input":{"tool":"calculator","arguments":{}}, "depends_on":["B"]}] }'
    with pytest.raises(ValueError):
        p._parse_plan(response)


def test_failed_dependency_blocks_downstream_tasks():
    # A -> B -> C ; simulate A failure
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["B"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = FakeExecutionManager(fail_tasks=["A"])

    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth())

    resp = agent.run("q")
    # A should be attempted and fail; B and C should be blocked (observations marked blocked)
    obs_meta = [o.metadata for o in resp.trace]
    # find blocked metadata entries
    blocked = [m for m in obs_meta if m and m.get("blocked")]
    assert len(blocked) >= 2
    # Agent response should indicate failure (replanning attempted)
    assert resp.success is False

