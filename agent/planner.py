import json

from core.contracts.execution import (
    Intent,
    Plan,
    Task,
)


class Planner:

    def __init__(self, model_gateway):

        self.model_gateway = model_gateway

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

IMPORTANT RULES:

- "What is EC2?" -> retrieval
- "Explain what Python is." -> retrieval
- "What is AWS Lambda?" -> retrieval
- "Calculate 24 * 7" -> tool
- "Calculate 100 / 4" -> tool
- "What is 25 + 30?" -> tool because it is an arithmetic operation.
- "What is EC2?" -> retrieval because EC2 is a knowledge topic.
- Never classify a normal knowledge question as tool.

For a retrieval intent, entities should contain:

{{
    "topic": "the main topic"
}}

For a tool intent, entities MUST contain:

{{
    "tool": "calculator",
    "math_expression": "the mathematical expression"
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

User: Calculate 24 * 7

Output:
{{
    "intent": "tool",
    "confidence": 1.0,
    "entities": {{
        "tool": "calculator",
        "math_expression": "24 * 7"
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

                expression = intent.entities.get(
                    "math_expression"
                )

                if tool_name != "calculator":

                    raise ValueError(
                        "Tool intent must specify calculator."
                    )

                if not expression:

                    raise ValueError(
                        "Calculator intent is missing "
                        "math_expression."
                    )

                if expression == "the mathematical expression":

                    raise ValueError(
                        "Calculator intent contains a "
                        "placeholder instead of an expression."
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
        intent: Intent,
        observation=None,
    ) -> Plan:

        if observation is not None:

            print("\n[Planner previous observation]")
            print(observation.summary)
            print(observation.error)
            print("[End previous observation]\n")


        # --------------------------------
        # Multi-task request
        # --------------------------------

        if " and " in query.lower():

            parts = query.split(
                " and ",
                1,
            )

            tasks = []

            for index, part in enumerate(parts):

                sub_intent = self.understand_intent(
                    part.strip()
                )

                sub_plan = self.create_plan(
                    part.strip(),
                    sub_intent,
                )

                for task in sub_plan.tasks:

                    task.id = (
                        f"task-{index + 1}"
                    )

                    tasks.append(task)

            return Plan(
                tasks=tasks
            )    

        task = self._create_task_from_intent(
            query=query,
            intent=intent,
            task_id="task-1",
        )

        return Plan(
            tasks=[task]
        )

    def _create_task_from_intent(
        self,
        query: str,
        intent: Intent,
        task_id: str = "task-1",
    ) -> Task:

        # --------------------------------
        # Retrieval
        # --------------------------------

        if intent.name == "retrieval":

            return Task(
                id=task_id,

                description=(
                    "Retrieve relevant information "
                    "from the knowledge base."
                ),

                input={
                    "query": query
                },

                metadata={
                    "capability": "retrieval"
                },
            )

        # --------------------------------
        # Tool
        # --------------------------------

        if intent.name == "tool":

            tool_name = intent.entities.get(
                "tool"
            )

            if tool_name == "calculator":

                arguments = {
                    "expression": intent.entities.get(
                        "math_expression",
                        ""
                    )
                }

            else:

                arguments = {
                    key: value
                    for key, value in intent.entities.items()
                    if key != "tool"
                }

            return Task(
                id=task_id,

                description=(
                    f"Execute the {tool_name} tool."
                ),

                input={
                    "tool": tool_name,
                    "arguments": arguments,
                },

                metadata={
                    "capability": "tool"
                },
            )

        # --------------------------------
        # General
        # --------------------------------

        return Task(
            id=task_id,

            description=(
                "Generate a direct response."
            ),

            input={
                "query": query
            },

            metadata={
                "capability": "model"
            },
        )


    def replan(
        self,
        query: str,
        observation,
        failed_task,
    ) -> Plan:

        print("\n[Failed task]")
        print("Description:", failed_task.description)
        print("Input:", failed_task.input)
        print("Metadata:", failed_task.metadata)
        print("[End failed task]\n")

        prompt = f"""
You are replanning an agent task.

Original user request:
{query}

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

Create a new single recovery task that addresses the failed task.

Do NOT recreate tasks that have already completed successfully.

Focus on recovering from the failed task using the previous
execution result and error.

The "intent" field MUST be exactly one of:

"retrieval"
"tool"
"general"

Return ONLY valid JSON.
Do NOT add explanations.
Do NOT add markdown.

The JSON must contain:

For a calculator task, the entities MUST contain:

{{
    "tool": "calculator",
    "math_expression": "the actual expression"
}}

For a retrieval task:

{{
    "topic": "the topic"
}}

For a general task:

{{

}}

Example:

Failed task input:
{{"tool": "calculator", "arguments": {{"expression": "abc"}}}}

Previous error:
Invalid calculation

A valid response is:

{{
    "intent": "general",
    "confidence": 1.0,
    "entities": {{}}
}}

Return ONLY valid JSON.
"""
        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=100,
            do_sample=False,
        )

        intent = self._parse_intent(
            response
        )

        recovery_query = failed_task.input.get("query", query)

        recovery_task = self._create_task_from_intent(
            query=recovery_query,
            intent=intent,
            task_id=failed_task.id,
        )

        return Plan(
            tasks=[recovery_task]
        )


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

                expression = intent.entities.get(
                    "math_expression"
                )

                if tool_name != "calculator":

                    raise ValueError(
                        "Tool intent must specify calculator."
                    )

                if not expression:

                    raise ValueError(
                        "Calculator intent is missing "
                        "math_expression."
                    )

                if expression == "the mathematical expression":

                    raise ValueError(
                        "Calculator intent contains "
                        "a placeholder."
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