from core.contracts.execution import Task, Plan
from agent.agent import Agent
from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager
from core.workflows.registry import WorkflowRegistry


class SimpleWorkflow:
    name = "simple"
    description = "simple wf"
    input_schema = {"type": "object", "required": ["x"]}

    def build_tasks(self, workflow_input):
        # A produces x, B depends on A and uses its output
        return [
            Task(id="A", description="A", input={"value": workflow_input["x"]}, metadata={"capability": "tool"}),
            Task(id="B", description="B", input={"value": {"from_task": "A", "path": "value"}}, metadata={"capability": "tool"}, depends_on=["A"]),
        ]


class BadWorkflowMissingInput:
    name = "bad_missing_input"
    description = "bad wf"
    input_schema = {"type": "object", "required": ["y"]}

    def build_tasks(self, workflow_input):
        return [Task(id="A", description="A", input={"value": 1}, metadata={"capability": "tool"})]


class BadWorkflowBadDeps:
    name = "bad_deps"
    description = "bad deps"
    input_schema = {"type": "object", "required": ["x"]}

    def build_tasks(self, workflow_input):
        return [
            Task(id="A", description="A", input={"value": 1}, metadata={"capability": "tool"}),
            Task(id="B", description="B", input={"value": {"from_task": "A", "path": "value"}}, metadata={"capability": "tool"}),
        ]


class BadWorkflowCycle:
    name = "bad_cycle"
    description = "cycle wf"
    input_schema = {"type": "object", "required": ["x"]}

    def build_tasks(self, workflow_input):
        return [
            Task(id="A", description="A", input={}, metadata={"capability": "tool"}, depends_on=["C"]),
            Task(id="B", description="B", input={}, metadata={"capability": "tool"}, depends_on=["A"]),
            Task(id="C", description="C", input={}, metadata={"capability": "tool"}, depends_on=["B"]),
        ]


class FakePlanner:
    def __init__(self, plan: Plan):
        self._plan = plan

    def create_plan(self, query, conversation_context=None, intent=None, observation=None):
        return self._plan

    def replan(self, *args, **kwargs):
        return self._plan


class EchoExecutionManager:
    def execute(self, task, context):
        from core.contracts.execution import ExecutionResult

        return ExecutionResult(success=True, output=task.input)


class FakeResponseSynth:
    def synthesize(self, query, observations, conversation_context=None):
        return "synth"


from core.workflows.registry import WorkflowRegistry


def test_workflow_validates_and_runs():
    wf = SimpleWorkflow()
    wr = WorkflowRegistry()
    wr.register(wf)

    # planner returns a workflow task which references the workflow by name
    plan = Plan(tasks=[Task(id="wf1", description="wf", input={"workflow": "simple", "x": 3}, metadata={"capability": "workflow"})])
    planner = FakePlanner(plan)
    agent = Agent(execution_manager=EchoExecutionManager(), planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), workflow_registry=wr)

    resp = agent.run("q")
    assert resp.success is True
    # check that tasks A and B ran
    ids = [o.task_id for o in resp.trace]
    assert "A" in ids and "B" in ids


def test_workflow_missing_input_rejected():
    wf = BadWorkflowMissingInput()
    wr = WorkflowRegistry()
    wr.register(wf)
    plan = Plan(tasks=[Task(id="wf1", description="wf", input={"workflow": "bad_missing_input"}, metadata={"capability": "workflow"})])
    planner = FakePlanner(plan)
    agent = Agent(execution_manager=EchoExecutionManager(), planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), workflow_registry=wr)

    resp = agent.run("q")
    assert resp.success is False


def test_workflow_requires_declared_dependency_for_dataflow():
    wf = BadWorkflowBadDeps()
    wr = WorkflowRegistry()
    wr.register(wf)
    plan = Plan(tasks=[Task(id="wf1", description="wf", input={"workflow": "bad_deps", "x": 1}, metadata={"capability": "workflow"})])
    planner = FakePlanner(plan)
    agent = Agent(execution_manager=EchoExecutionManager(), planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), workflow_registry=wr)

    resp = agent.run("q")
    assert resp.success is False


def test_workflow_cycle_rejected():
    wf = BadWorkflowCycle()
    wr = WorkflowRegistry()
    wr.register(wf)
    plan = Plan(tasks=[Task(id="wf1", description="wf", input={"workflow": "bad_cycle", "x": 1}, metadata={"capability": "workflow"})])
    planner = FakePlanner(plan)
    agent = Agent(execution_manager=EchoExecutionManager(), planner=planner, observer=Observer(), decision_maker=DecisionMaker(), context_manager=ContextManager(), response_synthesizer=FakeResponseSynth(), workflow_registry=wr)

    resp = agent.run("q")
    assert resp.success is False
