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
