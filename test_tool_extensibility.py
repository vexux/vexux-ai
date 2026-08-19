from typing import Any, Dict
from core.contracts.capabilities import ToolContract
from core.contracts.execution import Task, Plan, AgentContext, ExecutionResult, Intent
from core.contracts.observation import Observation
from core.contracts.response import AgentResponse
from core.context.context_manager import ContextManager
from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from core.tools.string_formatter import StringFormatterTool
from core.tools.text_analyzer import TextAnalyzerTool
from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from agent.agent import Agent


class MockModelGateway:
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
    def ask(self, query: str) -> str:
        return f"Retrieved knowledge for: {query}"


# ==============================================================================
# TEST 1: CalculatorTool behavior preserved
# ==============================================================================
def test_calculator_tool_preservation():
    calc = CalculatorTool()
    assert calc.name == "calculator"
    assert "arithmetic" in calc.description

    res = calc.execute({"expression": "100 / 4 + 5"})
    assert res == 30.0

    try:
        calc.execute({"expression": "invalid +++ syntax"})
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        assert "Invalid calculation" in str(exc)


# ==============================================================================
# TEST 2: ToolRegistry registers and retrieves tools
# ==============================================================================
def test_tool_registry_registration_and_retrieval():
    registry = ToolRegistry()
    calc = CalculatorTool()
    formatter = StringFormatterTool()

    registry.register(calc)
    registry.register(formatter)

    assert "calculator" in registry.list_tools()
    assert "string_formatter" in registry.list_tools()
    assert registry.get("calculator") is calc
    assert registry.get("string_formatter") is formatter

    # Duplicate registration must raise ValueError
    try:
        registry.register(calc)
        assert False, "Should have raised ValueError on duplicate registration"
    except ValueError as exc:
        assert "already registered" in str(exc)

    # Getting an unregistered tool must raise KeyError
    try:
        registry.get("non_existent_tool")
        assert False, "Should have raised KeyError on unknown tool"
    except KeyError as exc:
        assert "Tool not found" in str(exc)


# ==============================================================================
# TEST 3: New Tool #1 (StringFormatterTool) executes successfully
# ==============================================================================
def test_string_formatter_tool():
    tool = StringFormatterTool()
    assert tool.name == "string_formatter"
    assert "Transforms text" in tool.description

    assert tool.execute({"text": "hello", "operation": "uppercase"}) == "HELLO"
    assert tool.execute({"text": "WORLD", "operation": "lowercase"}) == "world"
    assert tool.execute({"text": "abcde", "operation": "reverse"}) == "edcba"
    assert tool.execute({"text": "hello world", "operation": "title"}) == "Hello World"

    # Default operation is uppercase
    assert tool.execute({"text": "default"}) == "DEFAULT"

    # Missing text argument raises ValueError
    try:
        tool.execute({})
        assert False, "Should have raised ValueError on missing text"
    except ValueError as exc:
        assert "Missing required argument" in str(exc)

    # Unsupported operation raises ValueError
    try:
        tool.execute({"text": "test", "operation": "unknown_op"})
        assert False, "Should have raised ValueError on unsupported operation"
    except ValueError as exc:
        assert "Unsupported operation" in str(exc)


# ==============================================================================
# TEST 4: New Tool #2 (TextAnalyzerTool) executes successfully
# ==============================================================================
def test_text_analyzer_tool():
    tool = TextAnalyzerTool()
    assert tool.name == "text_analyzer"
    assert "Analyzes text" in tool.description

    result = tool.execute({"text": "Hello world\nSecond line"})
    assert isinstance(result, dict)
    assert result["char_count"] == 23
    assert result["word_count"] == 4
    assert result["line_count"] == 2

    # Empty text
    empty_result = tool.execute({"text": ""})
    assert empty_result["char_count"] == 0
    assert empty_result["word_count"] == 0
    assert empty_result["line_count"] == 0

    # Missing text argument
    try:
        tool.execute({})
        assert False, "Should have raised ValueError on missing text"
    except ValueError as exc:
        assert "Missing required argument" in str(exc)


# ==============================================================================
# TEST 5: ExecutionManager dispatches arbitrary registered tools
# ==============================================================================
def test_execution_manager_dispatches_arbitrary_tools():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(StringFormatterTool())
    registry.register(TextAnalyzerTool())

    exec_mgr = ExecutionManager(tool_registry=registry)
    context = AgentContext(request_id="test-req")

    # Dispatch calculator
    calc_task = Task(
        id="task-1",
        description="Calculate math",
        input={"tool": "calculator", "arguments": {"expression": "50 * 2"}},
        metadata={"capability": "tool"},
    )
    calc_res = exec_mgr.execute(calc_task, context)
    assert calc_res.success is True
    assert calc_res.output == 100

    # Dispatch string_formatter
    format_task = Task(
        id="task-2",
        description="Format string",
        input={"tool": "string_formatter", "arguments": {"text": "vexux", "operation": "uppercase"}},
        metadata={"capability": "tool"},
    )
    format_res = exec_mgr.execute(format_task, context)
    assert format_res.success is True
    assert format_res.output == "VEXUX"

    # Dispatch text_analyzer
    analyze_task = Task(
        id="task-3",
        description="Analyze text",
        input={"tool": "text_analyzer", "arguments": {"text": "Vexux AI is awesome"}},
        metadata={"capability": "tool"},
    )
    analyze_res = exec_mgr.execute(analyze_task, context)
    assert analyze_res.success is True
    assert analyze_res.output == {"char_count": 19, "word_count": 4, "line_count": 1}


# ==============================================================================
# TEST 6: Unknown tool produces controlled ExecutionResult failure
# ==============================================================================
def test_unknown_tool_controlled_failure():
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    exec_mgr = ExecutionManager(tool_registry=registry)
    context = AgentContext(request_id="test-req")

    unknown_task = Task(
        id="task-unknown",
        description="Execute unknown tool",
        input={"tool": "unregistered_database_tool", "arguments": {}},
        metadata={"capability": "tool"},
    )
    result = exec_mgr.execute(unknown_task, context)
    assert result.success is False
    assert "Tool not found: unregistered_database_tool" in result.error

    # Missing tool field
    missing_tool_task = Task(
        id="task-missing",
        description="Missing tool field",
        input={"arguments": {}},
        metadata={"capability": "tool"},
    )
    missing_res = exec_mgr.execute(missing_tool_task, context)
    assert missing_res.success is False
    assert "missing 'tool' field" in missing_res.error


# ==============================================================================
# TEST 7: Agent executes newly registered tools without changes to Agent
# ==============================================================================
def test_agent_executes_new_tools_without_agent_modifications():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User request:\nFormat text hello to uppercase",
        '{"tasks": [{"id": "task-1", "description": "Format text", '
        '"capability": "tool", "input": {"tool": "string_formatter", '
        '"arguments": {"text": "hello", "operation": "uppercase"}}}]}',
    )

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(StringFormatterTool())
    registry.register(TextAnalyzerTool())

    execution_manager = ExecutionManager(
        retrieval=MockRetrieval(),
        tool_registry=registry,
        model_gateway=gateway,
    )
    planner = Planner(
        model_gateway=gateway,
        tool_registry=registry,
    )
    observer = Observer()
    decision_maker = DecisionMaker()
    context_manager = ContextManager()
    response_synthesizer = ResponseSynthesizer(model_gateway=gateway)

    agent = Agent(
        execution_manager=execution_manager,
        planner=planner,
        observer=observer,
        decision_maker=decision_maker,
        context_manager=context_manager,
        response_synthesizer=response_synthesizer,
    )

    response = agent.run("Format text hello to uppercase")

    assert response.success is True
    assert response.output == "HELLO"
    assert len(response.trace) == 1
    assert response.trace[0].success is True
    assert response.trace[0].output == "HELLO"
    assert response.trace[0].task_id == "task-1"


def test_planner_prompt_uses_registered_tool_descriptions():
    gateway = MockModelGateway()
    gateway.set_response_for(
        "User: Echo this message",
        '{"intent": "tool", "confidence": 1.0, "entities": '
        '{"tool": "custom_echo", "arguments": '
        '{"message": "hello"}}}',
    )

    registry = ToolRegistry()
    registry.register(CustomThirdPartyEchoTool())

    planner = Planner(
        model_gateway=gateway,
        tool_registry=registry,
    )

    intent = planner.understand_intent(
        "Echo this message"
    )

    assert intent.name == "tool"
    assert "custom_echo" in gateway.recorded_prompts[0]
    assert "Echoes the provided message with prefix." in gateway.recorded_prompts[0]


# ==============================================================================
# TEST 8: Custom Third-Party Tool pluggability without core modification
# ==============================================================================
class CustomThirdPartyEchoTool:
    """A third-party custom tool written outside core to prove plug-and-play extensibility."""
    @property
    def name(self) -> str:
        return "custom_echo"

    @property
    def description(self) -> str:
        return "Echoes the provided message with prefix."

    def execute(self, arguments: Dict[str, Any]) -> str:
        msg = arguments.get("message", "")
        return f"[ECHO]: {msg}"


def test_custom_third_party_tool_pluggability():
    registry = ToolRegistry()
    registry.register(CustomThirdPartyEchoTool())

    exec_mgr = ExecutionManager(tool_registry=registry)
    context = AgentContext(request_id="echo-req")

    task = Task(
        id="task-echo",
        description="Echo custom message",
        input={"tool": "custom_echo", "arguments": {"message": "Extensibility works!"}},
        metadata={"capability": "tool"},
    )

    res = exec_mgr.execute(task, context)
    assert res.success is True
    assert res.output == "[ECHO]: Extensibility works!"


if __name__ == "__main__":
    tests = [
        test_calculator_tool_preservation,
        test_tool_registry_registration_and_retrieval,
        test_string_formatter_tool,
        test_text_analyzer_tool,
        test_execution_manager_dispatches_arbitrary_tools,
        test_unknown_tool_controlled_failure,
        test_agent_executes_new_tools_without_agent_modifications,
        test_custom_third_party_tool_pluggability,
    ]

    print("=" * 60)
    print("Running Tool Extensibility Test Suite")
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
