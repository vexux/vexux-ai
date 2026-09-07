from agent.observer import Observer
from core.contracts.execution import ExecutionResult, Task
from core.security.redaction import redact_sensitive_data
from core.tools.calculator import CalculatorTool
from core.tools.registry import ToolRegistry


def test_sensitive_values_are_redacted_from_observations():
    observation = Observer().observe(
        ExecutionResult(success=False, error="Bearer test-secret-token"),
        Task(id="task", description="task"),
    )

    assert "test-secret-token" not in observation.error
    assert "[REDACTED]" in observation.error


def test_tool_security_metadata_is_discoverable():
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    assert registry.describe_tools()[0]["security_metadata"] == {
        "requires_network": False,
        "requires_secret": False,
        "side_effects": False,
    }
