import json
import re

from core.contracts.execution import Intent, Plan, Task
from core.tools.registry import ToolRegistry


class Planner:

    SUPPORTED_CAPABILITIES = {
        "retrieval",
        "tool",
        "model",
        "workflow",
    }

    def __init__(
        self,
        model_gateway,
        tool_registry: ToolRegistry,
        knowledge_source_registry=None,
        knowledge_graph_registry=None,
        workflow_registry=None,
    ):

        self.model_gateway = model_gateway
        self.tool_registry = tool_registry

        self.knowledge_source_registry = knowledge_source_registry
        self.knowledge_graph_registry = knowledge_graph_registry
        self.workflow_registry = workflow_registry

    def _tool_descriptions(self) -> str:

        tool_metadata = self.tool_registry.describe_tools()

        return json.dumps(tool_metadata, indent=2) if tool_metadata else "No tools are registered."

    def _knowledge_source_descriptions(self) -> str:

        if self.knowledge_source_registry is None:
            return "No knowledge sources are registered."

        sources = self.knowledge_source_registry.describe_sources()

        return json.dumps(sources, indent=2) if sources else "No knowledge sources are registered."

    def _workflow_descriptions(self) -> str:

        if self.workflow_registry is None:
            return "No workflows are registered."

        workflows = self.workflow_registry.describe_workflows()

        return json.dumps(workflows, indent=2) if workflows else "No workflows are registered."

    def _deterministic_plan(self, query: str) -> Plan | None:
        """Select unambiguous capabilities without relying on model formatting."""
        if self.workflow_registry is None:
            return None

        has_customer_workflow = any(
            "customer_id" in set(item.get("input_schema", {}).get("required", []))
            for item in self.workflow_registry.describe_workflows()
        )
        if not has_customer_workflow:
            return None

        normalized = query.strip().lower()
        if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening)[!. ]*", normalized):
            return Plan(tasks=[Task(
                id="task_1",
                description="Answer the user's greeting",
                input={"query": query},
                metadata={"capability": "model"},
            )])

        if re.match(r"^(?:what is|what are|who is|where is|when did|define|explain)\b", normalized):
            return Plan(tasks=[Task(
                id="task_1",
                description="Retrieve factual information",
                input={"query": query},
                metadata={"capability": "retrieval"},
            )])

        if self.workflow_registry is not None and re.search(
            r"\binvestigat(?:e|ion|ing)\b|\bsuspicious activity\b",
            normalized,
        ):
            identifier_match = re.search(r"\b[A-Z]\d+\b", query)
            if identifier_match is not None:
                workflow_name = None
                for metadata in self.workflow_registry.describe_workflows():
                    required = set(metadata.get("input_schema", {}).get("required", []))
                    if "customer_id" in required:
                        workflow_name = metadata["name"]
                        break
                if workflow_name is not None:
                    return Plan(tasks=[Task(
                        id="task_1",
                        description="Run the registered customer investigation workflow",
                        input={
                            "workflow": workflow_name,
                            "query": query,
                            "customer_id": identifier_match.group(0),
                        },
                        metadata={"capability": "workflow", "workflow": workflow_name},
                    )])

        return None

    def _workflow_guardrail(self, query: str, plan: Plan) -> Plan:
        """Correct unambiguous model misclassification using registered metadata."""
        deterministic = self._deterministic_plan(query)
        return deterministic or plan

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
            response_format="json",
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

Registered knowledge sources:
{self._knowledge_source_descriptions()}

Registered workflows:
{self._workflow_descriptions()}

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
or "workflow".
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
- General conversation, greetings, and social messages MUST use capability "model".
- Generic factual or document questions MUST use capability "retrieval".
- An explicitly supported customer investigation MUST use the registered workflow
  whose input schema requires "customer_id"; do not use generic retrieval.
- Arithmetic or another registered operation MUST use capability "tool".
- Retrieval input MUST contain a string field named "query".
- Retrieval input may include "source" only when it exactly matches a registered knowledge source; omit it to use the default source.
- Model input MUST contain a string field named "query".
- Workflow input MUST contain a registered "workflow" name and satisfy its input schema.
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

        deterministic = self._deterministic_plan(query)
        if deterministic is not None:
            return deterministic

        response = self.model_gateway.generate(
            self._planning_prompt(query, conversation_context),
            max_new_tokens=500,
            do_sample=False,
            response_format="json",
        )

        return self._workflow_guardrail(query, self._parse_plan(response))

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

            # Validate dependencies after all tasks are parsed
            id_map = {t.id: t for t in tasks}

            # Validate dependency values: existence, no self-dependency
            for t in tasks:
                if not isinstance(t.depends_on, list):
                    raise ValueError(f"Task '{t.id}' has malformed 'depends_on' value; must be a list of task ids.")
                for dep in t.depends_on:
                    if dep == t.id:
                        raise ValueError(f"Task '{t.id}' has a self-dependency.")
                    if dep not in id_map:
                        raise ValueError(f"Task '{t.id}' depends on unknown task id: {dep}")

            # Detect cycles using Kahn's algorithm
            indegree = {t.id: 0 for t in tasks}
            adj = {t.id: [] for t in tasks}
            for t in tasks:
                for dep in t.depends_on:
                    adj[dep].append(t.id)
                    indegree[t.id] += 1

            queue = [nid for nid, deg in indegree.items() if deg == 0]
            seen = 0
            while queue:
                nid = queue.pop(0)
                seen += 1
                for nbr in adj.get(nid, []):
                    indegree[nbr] -= 1
                    if indegree[nbr] == 0:
                        queue.append(nbr)

            if seen != len(tasks):
                raise ValueError("Plan contains a cycle in task dependencies.")

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

        if capability == "retrieval" and "source" in task_input:
            source_name = task_input["source"]

            if not isinstance(source_name, str) or not source_name:
                raise ValueError(
                    f"Task {index} requires a valid knowledge source name."
                )

            found = False
            if self.knowledge_source_registry is not None:
                try:
                    self.knowledge_source_registry.get(source_name)
                    found = True
                except KeyError:
                    pass
            if self.knowledge_graph_registry is not None:
                try:
                    self.knowledge_graph_registry.get(source_name)
                    found = True
                except KeyError:
                    pass
            if not found:
                raise ValueError(
                    f"Task {index} references unknown knowledge resource: {source_name}"
                )

        if capability == "workflow":
            workflow_name = task_input.get("workflow")
            if not isinstance(workflow_name, str) or self.workflow_registry is None:
                raise ValueError(f"Task {index} requires a registered workflow.")
            try:
                workflow = self.workflow_registry.get(workflow_name)
            except KeyError as exc:
                raise ValueError(
                    f"Task {index} references unknown workflow: {workflow_name}"
                ) from exc

            for field in workflow.input_schema.get("required", []):
                if field not in task_input:
                    raise ValueError(
                        f"Task {index} is missing required workflow input: {field}"
                    )
            if not isinstance(task_input.get("query"), str) or not task_input["query"].strip():
                raise ValueError(f"Task {index} requires a non-empty workflow query.")

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

            self._validate_tool_arguments(
                tool_name,
                arguments,
                index,
            )

        depends_on = raw_task.get("depends_on") if isinstance(raw_task.get("depends_on"), list) else []

        return Task(
            id=task_id,
            description=description,
            input=task_input,
            metadata={"capability": capability},
            depends_on=depends_on,
        )

    def _validate_tool_arguments(
        self,
        tool_name: str,
        arguments: dict,
        index: int,
    ) -> None:

        schema = self.tool_registry.get(tool_name).input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for argument_name in required:
            if argument_name not in arguments:
                raise ValueError(
                    f"Task {index} is missing required argument "
                    f"'{argument_name}' for tool: {tool_name}"
                )

        for argument_name, specification in properties.items():
            if argument_name not in arguments:
                continue

            expected_type = specification.get("type")
            if expected_type == "string" and not isinstance(arguments[argument_name], str):
                raise ValueError(
                    f"Task {index} argument '{argument_name}' for tool "
                    f"{tool_name} must be a string."
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
CRITICAL: The recovered task MUST have the exact same task ID as the failed task.
Do not recreate tasks that already completed successfully.
Do not generate a new task ID.

Original request:
{query}

Previous conversation context:
{previous_conversation}

Failed task ID (YOU MUST PRESERVE THIS EXACT ID):
{failed_task.id}

Failed task details:
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

CRITICAL REQUIREMENTS:
- The task ID "{failed_task.id}" in the JSON output MUST be exactly this value.
- Do not modify, replace, or regenerate the task ID.
- The capability MUST be exactly one of "retrieval", "tool", or "model".
- Never combine capability values.
- Retrieval/model tasks require input.query as a non-empty string.
- Tool tasks require a registered input.tool and an object input.arguments.
- Preserve user expressions exactly.
""".strip()

        response = self.model_gateway.generate(
            prompt,
            max_new_tokens=300,
            do_sample=False,
            response_format="json",
        )

        plan = self._parse_plan(response)

        if len(plan.tasks) != 1:
            raise ValueError("Recovery plan must contain exactly one task.")

        if plan.tasks[0].id != failed_task.id:
            raise ValueError("Recovery task must preserve the failed task id.")

        return plan
