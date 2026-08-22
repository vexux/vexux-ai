from dataclasses import dataclass


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    policy_name: str = "default"


class DefaultPolicy:
    def __init__(self, max_input_length=10000, max_tasks=20):
        self.max_input_length = max_input_length
        self.max_tasks = max_tasks

    def validate_input(self, query):
        if not isinstance(query, str):
            return PolicyDecision(False, "Input must be a string.", "input_validation")
        if not query.strip():
            return PolicyDecision(False, "Input must not be empty.", "input_validation")
        if len(query) > self.max_input_length:
            return PolicyDecision(False, "Input exceeds maximum length.", "input_validation")
        return PolicyDecision(True)

    def validate_plan(self, plan, context):
        if len(plan.tasks) > self.max_tasks:
            return PolicyDecision(False, "Plan exceeds maximum task count.", "execution_limits")
        return PolicyDecision(True)

    def authorize_execution(self, task, context):
        return PolicyDecision(True)

    def validate_output(self, output, context):
        if not isinstance(output, str):
            return PolicyDecision(False, "Final output must be a string.", "output_validation")
        return PolicyDecision(True)
