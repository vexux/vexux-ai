from core.contracts.execution import Task


class KnowledgeGroundedAnswerWorkflow:
    name = "knowledge_grounded_answer"
    description = "Retrieve grounded knowledge and synthesize a sourced answer."
    input_schema = {"type": "object", "required": ["query"]}

    def build_tasks(self, workflow_input):
        return [Task(id="workflow-retrieve", description="Retrieve grounded knowledge", input={"query": workflow_input["query"]}, metadata={"capability": "retrieval", "workflow": self.name, "step": "retrieve"})]
