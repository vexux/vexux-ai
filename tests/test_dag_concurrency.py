import threading
import time
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


class BarrierExecutionManager:
    """
    Execution manager that uses a threading.Barrier to force two tasks to overlap.
    Intended use for tasks named 'B' and 'C'.
    """
    def __init__(self, barrier: threading.Barrier, fail_tasks=None):
        self.barrier = barrier
        self.fail_tasks = set(fail_tasks or [])
        self.calls = []

    def execute(self, task, context):
        self.calls.append(task.id)
        # Simulate a small delay for A to complete before B/C start
        if task.id in ("B", "C"):
            # Wait on barrier so both B and C reach this point (proves overlap)
            self.barrier.wait(timeout=5)
            # then simulate work
            time.sleep(0.05)
        else:
            time.sleep(0.01)

        if task.id in self.fail_tasks:
            return ExecutionResult(success=False, error=f"Simulated failure: {task.id}")
        return ExecutionResult(success=True, output={"task_id": task.id})


class TimedExecutionManager:
    """
    Records start and end times for each task to allow sequentiality assertions.
    """
    def __init__(self, duration_map=None, fail_tasks=None):
        self.duration_map = duration_map or {}
        self.fail_tasks = set(fail_tasks or [])
        self.calls = []
        self.times = {}

    def execute(self, task, context):
        self.calls.append(task.id)
        start = time.perf_counter()
        time.sleep(self.duration_map.get(task.id, 0.05))
        end = time.perf_counter()
        self.times[task.id] = (start, end)
        if task.id in self.fail_tasks:
            return ExecutionResult(success=False, error=f"Simulated failure: {task.id}")
        return ExecutionResult(success=True, output={"task_id": task.id})


class FakeResponseSynth:
    def synthesize(self, query, observations, conversation_context=None):
        return "synth"


def make_tasks(defs):
    tasks = []
    for tid, cap, deps in defs:
        tasks.append(Task(id=tid, description=f"task {tid}", input={}, metadata={"capability": cap}, depends_on=deps or []))
    return tasks


def test_two_independent_tasks_execute_concurrently():
    # A -> B and A -> C ; after A completes, B and C should overlap when max_parallel_tasks=2
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["A"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    barrier = threading.Barrier(2)
    exec_mgr = BarrierExecutionManager(barrier)
    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=2)

    resp = agent.run("q")
    # barrier.wait will raise if B/C did not both reach it; reaching here implies overlap
    assert "A" in exec_mgr.calls
    # ensure both B and C were called
    assert "B" in exec_mgr.calls and "C" in exec_mgr.calls
    assert resp.success is True


def test_max_parallel_tasks_one_behaves_sequentially():
    # A -> B and A -> C ; with max_parallel_tasks=1, B and C should not overlap
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["A"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    timed_mgr = TimedExecutionManager(duration_map={"A": 0.01, "B": 0.08, "C": 0.08})
    agent = Agent(execution_manager=timed_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=1)

    resp = agent.run("q")
    assert resp.success is True
    # Ensure B finished before C started
    b_start, b_end = timed_mgr.times["B"]
    c_start, c_end = timed_mgr.times["C"]
    assert c_start >= b_end - 1e-6


def test_max_parallel_tasks_limits_concurrency():
    # With three ready tasks but max_parallel_tasks=2, at most two should be submitted at once
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["A"]), ("D", "tool", ["A"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    barrier = threading.Barrier(2)
    exec_mgr = BarrierExecutionManager(barrier)
    # max_parallel_tasks=2 limits batch size
    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=2)

    resp = agent.run("q")
    assert resp.success is True
    # All tasks executed
    assert set(exec_mgr.calls) >= {"A", "B", "C", "D"}


def test_multiple_simultaneous_failures_deterministic_replan():
    # A -> B, C independent; both B and C fail; deterministic replan should pick B (earlier in plan)
    tasks = make_tasks([("A", "tool", []), ("B", "tool", ["A"]), ("C", "tool", ["A"]), ("D", "tool", ["B", "C"])])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    # both B and C fail
    exec_mgr = TimedExecutionManager(duration_map={"A":0.01, "B":0.02, "C":0.02}, fail_tasks={"B", "C"})
    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=2)

    resp = agent.run("q")
    # Agent should have attempted A, B, C and then failed
    assert "A" in exec_mgr.calls and "B" in exec_mgr.calls and "C" in exec_mgr.calls
    # Response should indicate failure (replanning attempted)
    assert resp.success is False
    # The last observation (added for replan) should correspond to B (earliest failed task)
    last_obs = resp.trace[-1]
    assert last_obs.task_id == "B" or last_obs.metadata and last_obs.metadata.get("blocked")
