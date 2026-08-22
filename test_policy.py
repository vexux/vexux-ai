from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from core.contracts.execution import AgentContext, Plan, Task
from core.policy.default import DefaultPolicy, PolicyDecision


def test_input_policy_rejects_empty_and_oversized_input():
    policy = DefaultPolicy(max_input_length=3)

    assert policy.validate_input(" ").allowed is False
    assert policy.validate_input("toolong").allowed is False
    assert policy.validate_input("ok").allowed is True


def test_plan_and_output_policy_limits_are_controlled():
    policy = DefaultPolicy(max_tasks=1)
    context = AgentContext(request_id="request")
    task = Task(id="task", description="task")

    assert policy.validate_plan(Plan(tasks=[task, task]), context).allowed is False
    assert policy.validate_output({}, context).allowed is False
    assert policy.validate_output("answer", context).allowed is True


def test_execution_denial_is_observable_in_observation_trace():
    class DenyingPolicy(DefaultPolicy):
        def authorize_execution(self, task, context):
            return PolicyDecision(False, "Denied for test.", "test_policy")

    task = Task(id="task", description="task", metadata={"capability": "tool"})
    result = ExecutionManager(policy=DenyingPolicy()).execute(
        task, AgentContext(request_id="request")
    )
    observation = Observer().observe(result, task)

    assert result.success is False
    assert "Policy denied execution" in result.error
    assert observation.metadata == {"policy": "test_policy", "reason": "Denied for test."}
