import json

import pytest

from agent.agent import Agent
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.observer import Observer
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from core.context.context_manager import ContextManager
from core.contracts.execution import AgentContext, Task
from core.tools.calculator import CalculatorTool
from core.tools.registry import ToolRegistry


class MockGateway:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response


def registry():
    tools = ToolRegistry()
    tools.register(CalculatorTool())
    return tools


def planner_for(response):
    tools = registry()
    return Planner(MockGateway(response), tools)


def plan(*tasks):
    return json.dumps({"tasks": list(tasks)})


def task(task_id, capability, task_input):
    return {
        "id": task_id,
        "description": f"Execute {task_id}",
        "capability": capability,
        "input": task_input,
    }


def test_single_retrieval_task():
    result = planner_for(
        plan(task("task-1", "retrieval", {"query": "EC2"}))
    ).create_plan("What is EC2?")

    assert len(result.tasks) == 1
    assert result.tasks[0].metadata["capability"] == "retrieval"
    assert result.tasks[0].input == {"query": "EC2"}


def test_single_tool_task():
    result = planner_for(
        plan(task("task-1", "tool", {
            "tool": "calculator",
            "arguments": {"expression": "24 * 7"},
        }))
    ).create_plan("Calculate 24 * 7")

    assert result.tasks[0].metadata["capability"] == "tool"
    assert result.tasks[0].input["tool"] == "calculator"
    assert result.tasks[0].input["arguments"] == {"expression": "24 * 7"}


def test_single_general_task():
    result = planner_for(
        plan(task("task-1", "model", {"query": "Hello"}))
    ).create_plan("Hello")

    assert result.tasks[0].metadata["capability"] == "model"
    assert result.tasks[0].input == {"query": "Hello"}


def test_missing_retrieval_query_is_rejected():
    response = plan(task("task-1", "retrieval", {}))

    with pytest.raises(ValueError, match="query"):
        planner_for(response).create_plan("What is EC2?")


def test_missing_model_query_is_rejected():
    response = plan(task("task-1", "model", {}))

    with pytest.raises(ValueError, match="query"):
        planner_for(response).create_plan("Hello")


def test_missing_tool_name_is_rejected():
    response = plan(task(
        "task-1",
        "tool",
        {"arguments": {}},
    ))

    with pytest.raises(ValueError, match="tool name"):
        planner_for(response).create_plan("Calculate 2 + 2")


def test_malformed_tool_arguments_are_rejected():
    response = plan(task(
        "task-1",
        "tool",
        {"tool": "calculator", "arguments": "abc"},
    ))

    with pytest.raises(ValueError, match="arguments"):
        planner_for(response).create_plan("Calculate abc")


def test_unknown_tool_is_rejected():
    response = plan(task(
        "task-1",
        "tool",
        {"tool": "unknown_tool", "arguments": {}},
    ))

    with pytest.raises(ValueError, match="unknown tool"):
        planner_for(response).create_plan("Use unknown tool")


def test_tool_schema_is_included_in_planner_prompt():
    class EchoTool:
        name = "echo"
        description = "Returns the supplied message."
        input_schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }

        def execute(self, arguments):
            return arguments["message"]

    tools = ToolRegistry()
    tools.register(EchoTool())
    gateway = MockGateway(plan(task(
        "task-1",
        "tool",
        {"tool": "echo", "arguments": {"message": "hello"}},
    )))

    Planner(gateway, tools).create_plan("Echo hello")

    assert '"name": "echo"' in gateway.prompts[0]
    assert '"description": "Returns the supplied message."' in gateway.prompts[0]
    assert '"required": [' in gateway.prompts[0]
    assert '"message"' in gateway.prompts[0]


def test_tool_arguments_are_validated_against_schema():
    missing_expression = plan(task(
        "task-1",
        "tool",
        {"tool": "calculator", "arguments": {}},
    ))
    with pytest.raises(ValueError, match="missing required argument 'expression'"):
        planner_for(missing_expression).create_plan("Calculate")

    non_string_expression = plan(task(
        "task-1",
        "tool",
        {"tool": "calculator", "arguments": {"expression": 42}},
    ))
    with pytest.raises(ValueError, match="must be a string"):
        planner_for(non_string_expression).create_plan("Calculate")


def test_ec2_and_invalid_calculation_is_planned_without_interpreting_abc():
    response = plan(
        task("task_1", "retrieval", {"query": "What is EC2?"}),
        task(
            "task_2",
            "tool",
            {
                "tool": "calculator",
                "arguments": {"expression": "abc"},
            },
        ),
    )

    result = planner_for(response).create_plan(
        "What is EC2 and calculate abc"
    )

    assert result.tasks[0].input["query"] == "What is EC2?"
    assert result.tasks[1].input["arguments"]["expression"] == "abc"


def test_retrieval_and_tool_multi_task():
    result = planner_for(
        plan(
            task("task-1", "retrieval", {"query": "EC2"}),
            task("task-2", "tool", {
                "tool": "calculator",
                "arguments": {"expression": "24 * 7"},
            }),
        )
    ).create_plan("What is EC2 and calculate 24 * 7")

    assert [item.metadata["capability"] for item in result.tasks] == [
        "retrieval",
        "tool",
    ]


def test_multiple_tool_tasks():
    result = planner_for(
        plan(
            task("task-1", "tool", {
                "tool": "calculator",
                "arguments": {"expression": "2 + 2"},
            }),
            task("task-2", "tool", {
                "tool": "calculator",
                "arguments": {"expression": "3 * 3"},
            }),
        )
    ).create_plan("Calculate 2 + 2 and calculate 3 * 3")

    assert len(result.tasks) == 2
    assert all(item.metadata["capability"] == "tool" for item in result.tasks)


def test_multiple_retrieval_tasks():
    result = planner_for(
        plan(
            task("task-1", "retrieval", {"query": "EC2"}),
            task("task-2", "retrieval", {"query": "Python"}),
        )
    ).create_plan("What is EC2 and what is Python?")

    assert len(result.tasks) == 2
    assert [item.input["query"] for item in result.tasks] == ["EC2", "Python"]


def test_invalid_planner_json_is_rejected():
    with pytest.raises(ValueError, match="Invalid structured plan response"):
        planner_for("not json").create_plan("Hello")


def test_missing_required_task_fields_are_rejected():
    response = plan({
        "id": "task-1",
        "description": "Missing capability",
        "input": {},
    })

    with pytest.raises(ValueError, match="unknown capability"):
        planner_for(response).create_plan("Hello")


def test_unknown_capability_is_rejected():
    response = plan(task("task-1", "database", {"query": "x"}))

    with pytest.raises(ValueError, match="unknown capability"):
        planner_for(response).create_plan("Query the database")


def test_pipe_separated_capability_is_rejected():
    response = plan(task(
        "task-1",
        "retrieval|tool|ec2",
        {"query": "EC2"},
    ))

    with pytest.raises(ValueError, match="unknown capability"):
        planner_for(response).create_plan("what is ec2")


def test_planning_prompt_lists_capabilities_without_pipe_placeholder():
    gateway = MockGateway(plan(task("task-1", "retrieval", {"query": "EC2"})))
    Planner(gateway, registry()).create_plan("what is ec2")

    prompt = gateway.prompts[0]
    assert '"capability": "retrieval"' in prompt
    assert 'retrieval|tool|model' not in prompt


def test_execution_manager_unknown_capability_is_controlled():
    manager = ExecutionManager(tool_registry=registry())

    result = manager.execute(
        Task(
            id="task-1",
            description="Unsupported operation",
            input={},
            metadata={"capability": "database"},
        ),
        AgentContext(request_id="test-request"),
    )

    assert result.success is False
    assert result.error == "Unknown capability: database"


def test_invalid_plan_returns_controlled_agent_failure():
    tools = registry()
    gateway = MockGateway("not json")
    planner = Planner(gateway, tools)
    agent = Agent(
        execution_manager=ExecutionManager(tool_registry=tools),
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=ResponseSynthesizer(gateway),
    )

    response = agent.run("Make a plan")

    assert response.success is False
    assert response.output is None
    assert response.error.startswith("Planning failed:")
    assert response.trace == []
