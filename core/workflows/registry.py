from core.contracts.execution import Plan, Task


class WorkflowRegistry:
    def __init__(self):
        self._workflows = {}

    def register(self, workflow):
        if workflow.name in self._workflows:
            raise ValueError(f"Workflow already registered: {workflow.name}")
        self._workflows[workflow.name] = workflow

    def get(self, name):
        if name not in self._workflows:
            raise KeyError(f"Workflow not found: {name}")
        return self._workflows[name]

    def describe_workflows(self):
        return [{"name": item.name, "description": item.description, "input_schema": item.input_schema} for item in self._workflows.values()]

    def plan_query(self, query: str) -> Task | Plan | None:
        """Ask registered workflows whether they own deterministic query matching."""
        for workflow in self._workflows.values():
            planner = getattr(workflow, "plan_query", None)
            if not callable(planner):
                continue
            task = planner(query)
            if task is not None:
                if isinstance(task, Plan):
                    if (
                        not task.tasks
                        or not all(isinstance(item, Task) for item in task.tasks)
                    ):
                        raise TypeError(
                            f"Workflow '{workflow.name}' plan_query must return "
                            "a non-empty Plan containing only Tasks."
                        )
                    ids = [item.id for item in task.tasks]
                    if len(ids) != len(set(ids)):
                        raise TypeError(
                            f"Workflow '{workflow.name}' plan_query must return "
                            "a Plan with unique Task IDs."
                        )
                    return task
                if not isinstance(task, Task):
                    raise TypeError(
                        f"Workflow '{workflow.name}' plan_query must return "
                        "a Task, Plan, or None."
                    )
                return task
        return None

    def supports_query_planning(self) -> bool:
        return any(
            callable(getattr(workflow, "plan_query", None))
            for workflow in self._workflows.values()
        )
