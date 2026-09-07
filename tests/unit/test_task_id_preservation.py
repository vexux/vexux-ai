"""Test to verify that recovery tasks preserve the failed task ID correctly."""

import json
from core.contracts.execution import Task
from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from agent.planner import Planner


class MockModelGateway:
    """Mock Model Gateway for testing recovery task ID preservation."""

    def __init__(self):
        self.recorded_prompts = []
        self.handlers = []

    def set_response_for(self, substring: str, response: str):
        self.handlers.append((substring, response))

    def generate(self, prompt: str, **kwargs) -> str:
        self.recorded_prompts.append(prompt)
        for pattern, resp in reversed(self.handlers):
            if pattern in prompt:
                return resp
        return '{"tasks": []}'


def test_recovery_prompt_explicitly_states_task_id_preservation():
    """Verify that the recovery prompt explicitly states the requirement to preserve task IDs."""
    gateway = MockModelGateway()
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    
    planner = Planner(
        model_gateway=gateway,
        tool_registry=registry,
    )
    
    # Create a failed task
    failed_task = Task(
        id="task_2",
        description="Calculate invalid expression",
        input={"tool": "calculator", "arguments": {"expression": "abc"}},
        metadata={"capability": "tool"},
    )
    
    # Create a mock observation
    class MockObservation:
        success = False
        summary = "Task 'task_2' failed: Invalid calculation"
        error = "name 'abc' is not defined"
    
    observation = MockObservation()
    
    # Set up the recovery response - a valid recovery task with same ID
    recovery_response = json.dumps({
        "tasks": [{
            "id": "task_2",
            "description": "Recovery: try alternative approach",
            "capability": "model",
            "input": {"query": "What is the result of abc?"},
        }]
    })
    
    gateway.set_response_for("structured recovery-planning component", recovery_response)
    
    # Call replan
    plan = planner.replan(
        query="What is EC2 and calculate abc",
        observation=observation,
        failed_task=failed_task,
    )
    
    # Verify the recovery task preserves the ID
    assert len(plan.tasks) == 1
    assert plan.tasks[0].id == "task_2", f"Expected task ID 'task_2', got '{plan.tasks[0].id}'"
    
    # Verify the recovery prompt was sent
    assert len(gateway.recorded_prompts) > 0
    recovery_prompt = gateway.recorded_prompts[0]
    
    # Verify the prompt contains all the critical requirements
    assert "CRITICAL: The recovered task MUST have the exact same task ID" in recovery_prompt, \
        "Prompt should explicitly state that task ID must be preserved"
    
    assert "Do not generate a new task ID" in recovery_prompt, \
        "Prompt should explicitly state not to generate a new task ID"
    
    assert 'Failed task ID (YOU MUST PRESERVE THIS EXACT ID):' in recovery_prompt, \
        "Prompt should highlight the task ID requirement"
    
    assert '"id": "task_2"' in recovery_prompt, \
        "Prompt should show the exact task ID in the template"
    
    assert '- The task ID "task_2" in the JSON output MUST be exactly this value.' in recovery_prompt, \
        "Prompt should explicitly state in CRITICAL REQUIREMENTS that the ID must match exactly"
    
    print("[PASS] Recovery prompt explicitly states task ID preservation requirement")
    print("[PASS] Recovery task successfully preserves failed task ID")


def test_recovery_validates_task_id_match():
    """Verify that replan() validation catches mismatched task IDs."""
    gateway = MockModelGateway()
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    
    planner = Planner(
        model_gateway=gateway,
        tool_registry=registry,
    )
    
    # Create a failed task
    failed_task = Task(
        id="task_2",
        description="Calculate invalid expression",
        input={"tool": "calculator", "arguments": {"expression": "abc"}},
        metadata={"capability": "tool"},
    )
    
    # Create a mock observation
    class MockObservation:
        success = False
        summary = "Task 'task_2' failed: Invalid calculation"
        error = "name 'abc' is not defined"
    
    observation = MockObservation()
    
    # Set up a WRONG recovery response - with a different ID
    wrong_recovery_response = json.dumps({
        "tasks": [{
            "id": "task_3",  # WRONG ID!
            "description": "Recovery: try alternative approach",
            "capability": "model",
            "input": {"query": "What is the result of abc?"},
        }]
    })
    
    gateway.set_response_for("structured recovery-planning component", wrong_recovery_response)
    
    # Call replan and expect it to fail
    try:
        plan = planner.replan(
            query="What is EC2 and calculate abc",
            observation=observation,
            failed_task=failed_task,
        )
        assert False, "Should have raised ValueError for mismatched task ID"
    except ValueError as e:
        assert "Recovery task must preserve the failed task id" in str(e), \
            f"Expected error about preserving task ID, got: {e}"
        print("[PASS] Recovery validation correctly rejects mismatched task IDs")


def test_recovery_works_with_multiple_task_ids():
    """Verify that recovery works correctly with different task IDs."""
    gateway = MockModelGateway()
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    
    planner = Planner(
        model_gateway=gateway,
        tool_registry=registry,
    )
    
    # Test with different task IDs
    test_cases = [
        ("task_1", "retrieval"),
        ("task_2", "tool"),
        ("task_3", "model"),
        ("task_abc_xyz", "retrieval"),
    ]
    
    class MockObservation:
        success = False
        summary = "Task failed"
        error = "Some error"
    
    for task_id, capability in test_cases:
        failed_task = Task(
            id=task_id,
            description="Some task",
            input={"query": "test"},
            metadata={"capability": capability},
        )
        
        # Set up recovery response with matching ID
        recovery_response = json.dumps({
            "tasks": [{
                "id": task_id,
                "description": "Recovery task",
                "capability": "model",
                "input": {"query": "recovery"},
            }]
        })
        
        gateway.set_response_for("structured recovery-planning component", recovery_response)
        
        # Call replan
        plan = planner.replan(
            query="Test query",
            observation=MockObservation(),
            failed_task=failed_task,
        )
        
        # Verify the ID is preserved
        assert plan.tasks[0].id == task_id, \
            f"Failed to preserve task ID '{task_id}' (got '{plan.tasks[0].id}')"
        
        print(f"[PASS] Recovery preserves task ID: {task_id}")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Task ID Preservation in Recovery Planning")
    print("=" * 70)
    
    test_recovery_prompt_explicitly_states_task_id_preservation()
    test_recovery_validates_task_id_match()
    test_recovery_works_with_multiple_task_ids()
    
    print("=" * 70)
    print("All task ID preservation tests passed!")
    print("=" * 70)
