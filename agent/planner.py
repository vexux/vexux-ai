import json

from core.contracts.execution import (
    Intent,
    Plan,
    Task,
)
from core.tools.registry import ToolRegistry


class Planner:

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
    ) -> Intent:

        normalized_query = query.strip().lower()

        if normalized_query.startswith("calculate "):

            expression = query.strip()[
                len("calculate "):
            ].strip()

            return Intent(
                name="tool",
                confidence=1.0,
                entities={
                    "tool": "calculator",
                    "math_expression": expression,
                },
            )

        previous_context = ""

        if previous_observation is not None:

            previous_context = f"""
        Previous execution result:

        Success:
        {previous_observation.success}

        Summary:
        {previous_observation.summary}

        Error:
        {previous_observation.error}

        Use this information when deciding what should happen next.
        """

        prompt = f"""
You are an intent classifier for an AI agent.

You MUST classify the user request into exactly ONE
of these intents:

1. retrieval
   Use this when the user asks for factual information
   or wants information explained using the knowledge base.

2. tool
   Use this ONLY when the user explicitly asks to
   perform an operation such as a calculation.

3. general
   Use this for greetings, normal conversation,
   opinions, or requests that do not require retrieval
   or a tool.

Available tools:
{self._tool_descriptions()}

IMPORTANT RULES:

- "What is EC2?" -> retrieval
- "Explain what Python is." -> retrieval
- "What is AWS Lambda?" -> retrieval
- Requests to perform a registered operation -> tool
- "What is EC2?" -> retrieval because EC2 is a knowledge topic.
- Never classify a normal knowledge question as tool.

For a retrieval intent, entities should contain:

{{
    "topic": "the main topic"
}}

For a tool intent, entities MUST contain the selected tool name and
the arguments required by that tool:

{{
    "tool": "<registered tool name>",
    "arguments": {{}}
}}

For a general intent, entities should be empty.

Return ONLY valid JSON.
Do NOT add explanations.
Do NOT add markdown.
Do NOT wrap the JSON in ```.

Examples:

User: What is EC2?

Output:
{{
    "intent": "retrieval",
    "confidence": 1.0,
    "entities": {{
        "topic": "EC2"
    }}
}}

User: Explain what Python is.

Output:
{{
    "intent": "retrieval",
    "confidence": 1.0,
    "entities": {{
        "topic": "Python"
    }}
}}

User: Perform the registered tool operation

Output:
{{
    "intent": "tool",
    "confidence": 1.0,
    "entities": {{
        "tool": "<registered tool name>",
        "arguments": {{}}
    }}
}}

User: Hello

Output:
{{
    "intent": "general",
    "confidence": 1.0,
    "entities": {{}}
}}

Now classify this request:

User: {query}

{previous_context}
"""

        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=100,
            do_sample=False,
        )

        print("\n[Planner raw response]")
        print(response)
        print("[End planner response]\n")

        try:

            # --------------------------------
            # Clean model response
            # --------------------------------

            response = response.strip()

            if response.startswith("```"):

                lines = response.splitlines()

                # Remove opening ```json / ```
                if lines:
                    lines = lines[1:]

                # Remove closing ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                response = "\n".join(lines).strip()

            # --------------------------------
            # Parse JSON
            # --------------------------------

            data = json.loads(response)

            # --------------------------------
            # Build Intent
            # --------------------------------

            intent = Intent(
                name=data["intent"],
                confidence=float(
                    data.get("confidence", 0.0)
                ),
                entities=data.get(
                    "entities",
                    {}
                ),
            )

            # --------------------------------
            # Validate intent
            # --------------------------------

            allowed_intents = {
                "retrieval",
                "tool",
                "general",
            }

            if intent.name not in allowed_intents:

                raise ValueError(
                    f"Unknown intent: {intent.name}"
                )

            if not 0.0 <= intent.confidence <= 1.0:

                raise ValueError(
                    "Intent confidence must be between 0 and 1."
                )

            # --------------------------------
            # Validate entities
            # --------------------------------

            if not isinstance(
                intent.entities,
                dict
            ):

                raise ValueError(
                    "Intent entities must be a dictionary."
                )

            # --------------------------------
            # Validate tool intent
            # --------------------------------

            if intent.name == "tool":

                tool_name = intent.entities.get(
                    "tool"
                )

                if not tool_name:

                    raise ValueError(
                        "Tool intent must specify a tool name."
                    )

            return intent

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"Invalid intent response: {exc}"
            ) from exc


    def create_plan(
        self,
        query: str,
        intent: Intent = None,
        observation=None,
        conversation_context=None,
    ) -> Plan:

        conversation_context = conversation_context or []
        previous_conversation = "\n".join(
            f"User: {turn['query']}\nAssistant: {turn['response']}"
            for turn in conversation_context
        ) or "No previous conversation context."

        prompt = f"""
You are a planning component for an AI agent.

Create a sequential plan for this user request. Create one task for
each independent operation. Do not create dependencies between tasks.

User request:
{query}

Previous conversation context:
{previous_conversation}

Available tools:
{self._tool_descriptions()}

Return ONLY valid JSON in this exact shape:

{{
    "tasks": [
        {{
            "id": "task-1",
            "description": "short task description",
            "capability": "retrieval|tool|model",
            "input": {{}}
        }}
    ]
}}

Task rules:
- retrieval input MUST contain {{"query": "..."}}.
- tool input MUST contain {{"tool": "registered tool name", "arguments": {{}}}}.
- model input MUST contain {{"query": "..."}}.
- Use only the registered tools listed above.
- Preserve the order of independent operations from the request.
"""

        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=300,
            do_sample=False,
        )

        return self._parse_plan(response)

    def _parse_plan(self, response: str) -> Plan:

        response = response.strip()

        if response.startswith("```"):

            lines = response.splitlines()
            lines = lines[1:]

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

            for index, raw_task in enumerate(raw_tasks, start=1):

                if not isinstance(raw_task, dict):
                    raise ValueError(f"Task {index} must be a JSON object.")

                task_id = raw_task.get("id")
                description = raw_task.get("description")
                capability = raw_task.get("capability")
                task_input = raw_task.get("input")

                if not task_id or not isinstance(task_id, str):
                    raise ValueError(f"Task {index} is missing a valid 'id'.")

                if not description or not isinstance(description, str):
                    raise ValueError(
                        f"Task {index} is missing a valid 'description'."
                    )

                if capability not in {"retrieval", "tool", "model"}:
                    raise ValueError(
                        f"Task {index} has unknown capability: {capability}"
                    )

                if not isinstance(task_input, dict):
                    raise ValueError(
                        f"Task {index} is missing a valid 'input' object."
                    )

                if capability == "retrieval" or capability == "model":
                    if not isinstance(task_input.get("query"), str):
                        raise ValueError(
                            f"Task {index} requires a string 'query' input."
                        )

                if capability == "tool":
                    tool_name = task_input.get("tool")
                    arguments = task_input.get("arguments")

                    if not isinstance(tool_name, str) or not tool_name:
                        raise ValueError(
                            f"Task {index} requires a valid tool name."
                        )

                    if tool_name not in self.tool_registry.list_tools():
                        raise ValueError(
                            f"Task {index} references unknown tool: {tool_name}"
                        )

                    if not isinstance(arguments, dict):
                        raise ValueError(
                            f"Task {index} requires an 'arguments' object."
                        )

                tasks.append(
                    Task(
                        id=task_id,
                        description=description,
                        input=task_input,
                        metadata={"capability": capability},
                    )
                )

            return Plan(tasks=tasks)

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid structured plan response: {exc}") from exc


    def replan(
        self,
        query: str,
        observation,
        failed_task,
        conversation_context=None,
    ) -> Plan:

        conversation_context = conversation_context or []

        prompt = f"""
You are replanning an agent task.

Original user request:
{query}

Previous conversation context:
{conversation_context}

Failed task ID:
{failed_task.id}

    Failed task description:
    {failed_task.description}

    Failed task input:
    {failed_task.input}

    Failed task metadata:
    {failed_task.metadata}

    Previous execution result:

    Success:
    {observation.success}

    Summary:
    {observation.summary}

    Error:
    {observation.error}

    The previous task did not successfully complete.

    Available tools:
    {self._tool_descriptions()}

    Create a new single recovery task that addresses the failed task.

    Do NOT recreate tasks that have already completed successfully.

The "intent" field MUST be exactly one of:

"retrieval"
"tool"
"general"

Return ONLY valid JSON in this exact shape:

{{
    "tasks": [
        {{
            "id": "{failed_task.id}",
            "description": "recovery task",
            "capability": "retrieval|tool|model",
            "input": {{}}
        }}
    ]
}}
"""
        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=100,
            do_sample=False,
        )

        plan = self._parse_plan(response)

        if len(plan.tasks) != 1:
            raise ValueError("Recovery plan must contain exactly one task.")

        if plan.tasks[0].id != failed_task.id:
            raise ValueError("Recovery task must preserve the failed task id.")

        return plan


    def _parse_intent(
        self,
        response: str,
    ) -> Intent:

        response = response.strip()

        if response.startswith("```"):

            lines = response.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            response = "\n".join(lines).strip()

        try:

            data = json.loads(response)

            intent = Intent(
                name=data["intent"],
                confidence=float(
                    data.get("confidence", 0.0)
                ),
                entities=data.get(
                    "entities",
                    {}
                ),
            )

            allowed_intents = {
                "retrieval",
                "tool",
                "general",
            }

            if intent.name not in allowed_intents:

                raise ValueError(
                    f"Unknown intent: {intent.name}"
                )

            if not 0.0 <= intent.confidence <= 1.0:

                raise ValueError(
                    "Intent confidence must be between 0 and 1."
                )

            if not isinstance(
                intent.entities,
                dict
            ):

                raise ValueError(
                    "Intent entities must be a dictionary."
                )

            if intent.name == "tool":

                tool_name = intent.entities.get(
                    "tool"
                )

                if not tool_name:

                    raise ValueError(
                        "Tool intent must specify a tool name."
                    )

            return intent

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"Invalid intent response: {exc}"
            ) from exc