from core.contracts.execution import Task, Plan, ExecutionResult
from agent.agent import Agent
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
        return self._plan


class EchoExecutionManager:
    """ExecutionManager that echoes task.input as output."""
    def __init__(self, fail_tasks=None):
        self.fail_tasks = set(fail_tasks or [])
        self.calls = []

    def execute(self, task, context):
        self.calls.append(task.id)
        # Simulate failure if requested
        if task.id in self.fail_tasks:
            return ExecutionResult(success=False, output=None, error=f"Simulated failure: {task.id}")
        return ExecutionResult(success=True, output=task.input)


class FakeResponseSynth:
    def synthesize(self, query, observations, conversation_context=None):
        return "synth"


def make_tasks(defs):
    tasks = []
    for tid, cap, deps, inp in defs:
        tasks.append(Task(id=tid, description=f"task {tid}", input=inp or {}, metadata={"capability": cap}, depends_on=deps or []))
    return tasks


def test_sequential_task_output_dataflow():
    # A outputs {'value': 11}; B depends on A and references A's output
    tasks = make_tasks([
        ("A", "tool", [], {"value": 11}),
        ("B", "tool", ["A"], {"value": {"from_task": "A", "path": "value"}}),
    ])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = EchoExecutionManager()

    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=1)

    resp = agent.run("q")
    assert resp.success is True
    # find observation for B
    b_obs = [o for o in resp.trace if o.task_id == "B"][0]
    assert b_obs.output["value"] == 11


def test_parallel_task_output_dataflow():
    # A outputs {'value': 5}; B and C depend on A and reference its value; with parallelism both should resolve
    tasks = make_tasks([
        ("A", "tool", [], {"value": 5}),
        ("B", "tool", ["A"], {"value": {"from_task": "A", "path": "value"}}),
        ("C", "tool", ["A"], {"value": {"from_task": "A", "path": "value"}}),
    ])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = EchoExecutionManager()

    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=2)

    resp = agent.run("q")
    assert resp.success is True
    b_obs = [o for o in resp.trace if o.task_id == "B"][0]
    c_obs = [o for o in resp.trace if o.task_id == "C"][0]
    assert b_obs.output["value"] == 5
    assert c_obs.output["value"] == 5


def test_reference_missing_becomes_controlled_failure():
    # B references unknown task X -> resolution fails and B should fail
    tasks = make_tasks([
        ("A", "tool", [], {"value": 1}),
        ("B", "tool", ["A"], {"value": {"from_task": "X", "path": "value"}}),
    ])
    plan = Plan(tasks=tasks)
    planner = FakePlanner(plan)
    exec_mgr = EchoExecutionManager()

    agent = Agent(execution_manager=exec_mgr, planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), max_parallel_tasks=1)

    resp = agent.run("q")
    # Should have failed
    assert resp.success is False
    # B's observation should indicate failure
    b_obs = [o for o in resp.trace if o.task_id == "B"]
    assert b_obs
    assert b_obs[0].success is False
