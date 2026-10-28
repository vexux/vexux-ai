import json

import pytest

from agent.planner import Planner
from core.tools.registry import ToolRegistry
from core.workflows.knowledge_grounded_answer import KnowledgeGroundedAnswerWorkflow
from core.workflows.registry import WorkflowRegistry


class Gateway:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response


def test_workflow_registry_discovers_and_builds_deterministic_steps():
    registry = WorkflowRegistry()
    workflow = KnowledgeGroundedAnswerWorkflow()
    registry.register(workflow)

    assert registry.get(workflow.name) is workflow
    assert registry.describe_workflows()[0]["name"] == workflow.name
    tasks = workflow.build_tasks({"query": "What is EC2?"})
    assert [task.metadata["step"] for task in tasks] == ["retrieve"]
    assert tasks[0].input["query"] == "What is EC2?"


def test_planner_discovers_and_validates_workflow_selection():
    registry = WorkflowRegistry()
    registry.register(KnowledgeGroundedAnswerWorkflow())
    response = json.dumps({"tasks": [{
        "id": "workflow-1", "description": "Ground answer", "capability": "workflow",
        "input": {"workflow": "knowledge_grounded_answer", "query": "What is EC2?"},
    }]})
    gateway = Gateway(response)

    plan = Planner(gateway, ToolRegistry(), workflow_registry=registry).create_plan("What is EC2?")

    assert plan.tasks[0].metadata["capability"] == "workflow"
    assert "knowledge_grounded_answer" in gateway.prompts[0]


def test_unknown_workflow_is_rejected():
    response = json.dumps({"tasks": [{
        "id": "workflow-1", "description": "Unknown", "capability": "workflow",
        "input": {"workflow": "missing", "query": "query"},
    }]})

    with pytest.raises(ValueError, match="unknown workflow"):
        Planner(Gateway(response), ToolRegistry(), workflow_registry=WorkflowRegistry()).create_plan("query")
