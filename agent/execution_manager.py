from typing import Any

from core.contracts.execution import (
    AgentContext,
    ExecutionResult,
    Task,
)


class ExecutionManager:

    def __init__(
        self,
        retrieval=None,
        tool_registry=None,
        model_gateway=None,
    ):

        self.retrieval = retrieval

        self.tool_registry = tool_registry

        self.model_gateway = model_gateway

    def execute(
        self,
        task: Task,
        context: AgentContext,
    ) -> ExecutionResult:

        capability = task.metadata.get(
            "capability"
        )

        try:

            if capability == "retrieval":

                return self._execute_retrieval(
                    task
                )

            if capability == "tool":

                return self._execute_tool(
                    task
                )

            if capability == "model":

                return self._execute_model(
                    task
                )

            return ExecutionResult(
                success=False,
                error=(
                    f"Unknown capability: "
                    f"{capability}"
                ),
            )

        except Exception as exc:

            return ExecutionResult(
                success=False,
                error=str(exc),
            )

    def _execute_retrieval(
        self,
        task: Task,
    ) -> ExecutionResult:

        if self.retrieval is None:

            return ExecutionResult(
                success=False,
                error="Retrieval capability unavailable",
            )

        query = task.input["query"]
        top_k = task.input.get("top_k")

        if top_k is not None and (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k <= 0
        ):

            return ExecutionResult(
                success=False,
                error="Retrieval top_k must be a positive integer",
            )

        if hasattr(self.retrieval, "retrieve"):

            retrieved = self.retrieval.retrieve(
                query,
                k=top_k,
            ) if top_k is not None else self.retrieval.retrieve(query)

            if not retrieved:

                return ExecutionResult(
                    success=False,
                    output={
                        "query": query,
                        "results": [],
                        "context_found": False,
                    },
                    error="No sufficiently relevant retrieval context found",
                    metadata={"capability": "retrieval"},
                )

            result = {
                "query": query,
                "results": retrieved,
                "context_found": True,
            }

            return ExecutionResult(
                success=True,
                output=result,
                metadata={"capability": "retrieval"},
            )

        result = self.retrieval.ask(query)

        return ExecutionResult(
            success=True,
            output=result,
        )

    def _execute_tool(
        self,
        task: Task,
    ) -> ExecutionResult:

        if self.tool_registry is None:

            return ExecutionResult(
                success=False,
                error="Tool capability unavailable",
            )

        tool_name = task.input.get(
            "tool"
        )

        if not tool_name:

            return ExecutionResult(
                success=False,
                error="Task input missing 'tool' field",
            )

        arguments = task.input.get(
            "arguments",
            {}
        )

        try:

            result = self.tool_registry.execute(
                tool_name,
                arguments,
            )

            return ExecutionResult(
                success=True,
                output=result,
            )

        except KeyError:

            return ExecutionResult(
                success=False,
                error=f"Tool not found: {tool_name}",
            )

        except Exception as exc:

            return ExecutionResult(
                success=False,
                error=str(exc),
            )

    def _execute_model(
        self,
        task: Task,
    ) -> ExecutionResult:

        if self.model_gateway is None:

            return ExecutionResult(
                success=False,
                error="Model capability unavailable",
            )

        prompt = task.input["query"]

        result = self.model_gateway.generate(
            prompt
        )

        return ExecutionResult(
            success=True,
            output=result,
        )