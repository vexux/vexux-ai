import json

from core.contracts.execution import Intent, Plan, Task
from core.tools.registry import ToolRegistry


class Planner:

    SUPPORTED_CAPABILITIES = {
        "retrieval",
        "tool",
        "model",
    }

    def __init__(
        self,
        model_gateway,
        tool_registry: ToolRegistry,
    ):

        self.model_gateway = model_gateway
        self.tool_registry = tool_registry

    def _tool_descriptions(self) -> str:

        return "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool_name in self.tool_registry.list_tools()
            for tool in [self.tool_registry.get(tool_name)]
        ) or "- No tools are registered."

    def understand_intent(
        self,
        query: str,
        previous_observation=None,
    ):
        """Compatibility helper for callers that still request intent data."""

        prompt = f"""
Classify the user request into exactly one intent: retrieval, tool, or general.
Available tools:
{self._tool_descriptions()}
Return only JSON with intent, confidence, and entities.
User: {query}
""".strip()

        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=100,
            do_sample=False,
        ).strip()

        if response.startswith("```"):
            lines = response.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines).strip()

        try:
            data = json.loads(response)
            intent = data["intent"]
            confidence = float(data.get("confidence", 0.0))
            entities = data.get("entities", {})

            if intent not in {"retrieval", "tool", "general"}:
                raise ValueError(f"Unknown intent: {intent}")
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("Intent confidence must be between 0 and 1.")
            if not isinstance(entities, dict):
                raise ValueError("Intent entities must be a dictionary.")

            return Intent(
                name=intent,
                confidence=confidence,
                entities=entities,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid intent response: {exc}") from exc

    def _planning_prompt(
        self,
        query: str,
        conversation_context=None,
    ) -> str:

        conversation_context = conversation_context or []
        previous_conversation = "\n".join(
            f"User: {turn['query']}\nAssistant: {turn['response']}"
            for turn in conversation_context
        ) or "No previous conversation context."

        return f"""
You are a structured planning component for an AI agent.

Create a sequential plan for the user request. Create one task for
 each independent operation. Do not split text heuristically and do not
 create dependencies between tasks.

User request:
{query}

Previous conversation context:
{previous_conversation}

Registered tools:
{self._tool_descriptions()}

Return ONLY valid JSON. The top-level object MUST have this shape:

{{
  "tasks": [
    {{
      "id": "task_1",
      "description": "short task description",
      "capability": "retrieval",
      "input": {{"query": "What is EC2?"}}
    }}
  ]
}}

Every task MUST have exactly one capability. The capability value MUST
be exactly one of these strings: "retrieval", "tool", "model".
Never use a pipe-separated, combined, topic-based, or tool-based
capability value such as "retrieval|tool|ec2".

Canonical task examples:

Retrieval task:
{{
  "id": "task_1",
  "description": "Retrieve information about EC2",
  "capability": "retrieval",
  "input": {{"query": "What is EC2?"}}
}}

Tool task:
{{
  "id": "task_2",
  "description": "Calculate the expression",
  "capability": "tool",
  "input": {{"tool": "calculator", "arguments": {{"expression": "abc"}}}}
}}

Model task:
{{
  "id": "task_3",
  "description": "Answer the user's question",
  "capability": "model",
  "input": {{"query": "Hello"}}
}}

Multi-task example:
{{
  "tasks": [
    {{
      "id": "task_1",
      "description": "Retrieve information about EC2",
      "capability": "retrieval",
      "input": {{"query": "What is EC2?"}}
    }},
    {{
      "id": "task_2",
      "description": "Calculate the expression",
      "capability": "tool",
      "input": {{"tool": "calculator", "arguments": {{"expression": "24 * 7"}}}}
    }}
  ]
}}

Field rules:
- Retrieval input MUST contain a string field named "query".
- Model input MUST contain a string field named "query".
- Tool input MUST contain "tool" equal to a registered tool name and an object field named "arguments".
- Put topics and user text in input.query, never in capability.
- Preserve expressions exactly as provided. For example, use "abc" as the calculator expression; do not invent its meaning.
- Use only registered tool names.
- Preserve the order of independent operations.
""".strip()

    def create_plan(
        self,
        query: str,
        intent=None,
        observation=None,
        conversation_context=None,
    ) -> Plan:

        response = self.model_gateway.generate(
            self._planning_prompt(query, conversation_context),
            max_new_tokens=500,
            do_sample=False,
        )

        return self._parse_plan(response)

    def _parse_plan(self, response: str) -> Plan:

        response = response.strip()

        if response.startswith("```"):

            lines = response.splitlines()[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            response = "\n".join(lines).strip()

        try:
            data = json.loads(response)

            if not isinstance(data, dict):
                raise ValueError("Plan response must be a JSON object.")

            raw_tasks = data.get("tasks")

            if not isinstance(raw_tasks, list) or not raw_tasks:
                raise ValueError("Plan must contain a non-empty 'tasks' list.")

            tasks = []
            task_ids = set()

            for index, raw_task in enumerate(raw_tasks, start=1):
                tasks.append(self._parse_task(raw_task, index, task_ids))

            return Plan(tasks=tasks)

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid structured plan response: {exc}") from exc

    def _parse_task(
        self,
        raw_task,
        index: int,
        task_ids: set[str],
    ) -> Task:

        if not isinstance(raw_task, dict):
            raise ValueError(f"Task {index} must be a JSON object.")

        task_id = raw_task.get("id")
        description = raw_task.get("description")
        capability = raw_task.get("capability")
        task_input = raw_task.get("input")

        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"Task {index} is missing a valid 'id'.")

        if task_id in task_ids:
            raise ValueError(f"Task {index} duplicates task id: {task_id}")

        task_ids.add(task_id)

        if not isinstance(description, str) or not description:
            raise ValueError(f"Task {index} is missing a valid 'description'.")

        if capability not in self.SUPPORTED_CAPABILITIES:
            raise ValueError(f"Task {index} has unknown capability: {capability}")

        if not isinstance(task_input, dict):
            raise ValueError(f"Task {index} is missing a valid 'input' object.")

        if capability in {"retrieval", "model"}:
            query = task_input.get("query")

            if not isinstance(query, str) or not query.strip():
                raise ValueError(
                    f"Task {index} requires a non-empty string 'query' input."
                )

        if capability == "tool":
            tool_name = task_input.get("tool")
            arguments = task_input.get("arguments")

            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError(f"Task {index} requires a valid tool name.")

            if tool_name not in self.tool_registry.list_tools():
                raise ValueError(
                    f"Task {index} references unknown tool: {tool_name}"
                )

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Task {index} requires an 'arguments' object."
                )

        return Task(
            id=task_id,
            description=description,
            input=task_input,
            metadata={"capability": capability},
        )

    def replan(
        self,
        query: str,
        observation,
        failed_task,
        conversation_context=None,
    ) -> Plan:

        conversation_context = conversation_context or []
        previous_conversation = "\n".join(
            f"User: {turn['query']}\nAssistant: {turn['response']}"
            for turn in conversation_context
        ) or "No previous conversation context."

        prompt = f"""
You are a structured recovery-planning component for an AI agent.

Create exactly one recovery task for the failed task below.
Do not recreate tasks that already completed successfully.

Original request:
{query}

Previous conversation context:
{previous_conversation}

Failed task ID:
{failed_task.id}
{failed_task.description}
{failed_task.input}

Previous execution:
success={observation.success}
summary={observation.summary}
error={observation.error}

Registered tools:
{self._tool_descriptions()}

Return ONLY valid JSON with exactly one task in this canonical shape:
{{
  "tasks": [
    {{
      "id": "{failed_task.id}",
      "description": "recovery task",
      "capability": "model",
      "input": {{"query": "recovery request"}}
    }}
  ]
}}

The capability MUST be exactly one of "retrieval", "tool", or "model".
Never combine capability values. Retrieval/model tasks require input.query
as a non-empty string. Tool tasks require a registered input.tool and an
object input.arguments. Preserve user expressions exactly.
""".strip()

        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=300,
            do_sample=False,
        )

        plan = self._parse_plan(response)

        if len(plan.tasks) != 1:
            raise ValueError("Recovery plan must contain exactly one task.")

        if plan.tasks[0].id != failed_task.id:
            raise ValueError("Recovery task must preserve the failed task id.")

        return plan
