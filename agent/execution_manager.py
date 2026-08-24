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
        knowledge_source_registry=None,
        knowledge_graph_registry=None,
        policy=None,
    ):

        self.retrieval = retrieval

        self.tool_registry = tool_registry

        self.model_gateway = model_gateway

        self.knowledge_source_registry = knowledge_source_registry

        # New: optional graph registry
        self.knowledge_graph_registry = knowledge_graph_registry

        self.policy = policy

        # Create a KnowledgeDecision helper to normalize retrieval requests.
        try:
            from core.knowledge.decision import KnowledgeDecision
        except Exception:
            KnowledgeDecision = None

        self.knowledge_decision = KnowledgeDecision(
            rag=self.retrieval,
            knowledge_source_registry=self.knowledge_source_registry,
            knowledge_graph_registry=self.knowledge_graph_registry,
        ) if KnowledgeDecision is not None else None

    def execute(
        self,
        task: Task,
        context: AgentContext,
    ) -> ExecutionResult:

        capability = task.metadata.get(
            "capability"
        )

        try:

            if self.policy is not None:
                decision = self.policy.authorize_execution(task, context)
                if not decision.allowed:
                    return ExecutionResult(success=False, error=f"Policy denied execution: {decision.reason}", metadata={"policy": decision.policy_name, "reason": decision.reason})

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
                    task,
                    context.conversation_history,
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

        # Use the KnowledgeDecision component (if available) to normalize and
        # validate what kind of knowledge operation the task requests.
        query = task.input.get("query")
        explicit_source = task.input.get("source")
        top_k = task.input.get("top_k")

        if not isinstance(query, str) or not query.strip():
            return ExecutionResult(success=False, error="Retrieval task missing 'query' field")

        # If an explicit source was provided and a KnowledgeSourceRegistry exists,
        # attempt to use it directly. This preserves the original error message
        # behavior when a named source is missing (tests rely on the exact
        # KeyError text).
        if explicit_source and self.knowledge_source_registry is not None:
            try:
                source = self.knowledge_source_registry.get(explicit_source)
                return self._execute_retrieval_source(source, task)
            except KeyError as exc:
                # Preserve the original KeyError string representation
                return ExecutionResult(success=False, error=str(exc))

        if self.knowledge_decision is not None:
            try:
                kr = self.knowledge_decision.create_request(
                    query=query,
                    explicit_source=explicit_source,
                    operation=None,
                    params={"top_k": top_k} if top_k is not None else {},
                )
            except Exception as exc:
                # Controlled failure: explicit unknown source or unavailable capability
                return ExecutionResult(success=False, error=str(exc))

            # Route based on the KnowledgeRequest kind without performing any
            # cross-source fusion or multi-source retrieval.
            if kr.kind == "knowledge_source":
                try:
                    source = self.knowledge_source_registry.get(kr.source)
                except Exception as exc:
                    return ExecutionResult(success=False, error=str(exc))

                # Reuse existing source-based retrieval executor
                return self._execute_retrieval_source(source, task)

            if kr.kind == "rag":
                # Route to the RAG retrieval pipeline (self.retrieval). Keep the
                # historical behavior: do NOT inject a 'source' field for the
                # raw RAG pipeline path to preserve existing test expectations.
                if self.retrieval is None:
                    return ExecutionResult(success=False, error="Retrieval (RAG) capability unavailable")

                if top_k is not None and (
                    not isinstance(top_k, int)
                    or isinstance(top_k, bool)
                    or top_k <= 0
                ):
                    return ExecutionResult(success=False, error="Retrieval top_k must be a positive integer")

                if hasattr(self.retrieval, "retrieve"):
                    retrieved = self.retrieval.retrieve(query, k=top_k) if top_k is not None else self.retrieval.retrieve(query)

                    if not retrieved:
                        return ExecutionResult(
                            success=False,
                            output={"query": query, "results": [], "context_found": False},
                            error="No sufficiently relevant retrieval context found",
                            metadata={"capability": "retrieval"},
                        )

                    return ExecutionResult(success=True, output={"query": query, "results": retrieved, "context_found": True}, metadata={"capability": "retrieval"})

                result = self.retrieval.ask(query)
                return ExecutionResult(success=True, output=result, metadata={"capability": "retrieval"})

            if kr.kind == "graph":
                # Knowledge graph execution is out-of-scope for Phase 11. Return a
                # controlled failure indicating the decision is valid but execution
                # is not yet implemented.
                return ExecutionResult(success=False, error=f"Knowledge graph execution not implemented for graph: {kr.source}")

            # Fallback safety
            return ExecutionResult(success=False, error=f"Unsupported knowledge request kind: {kr.kind}")

        # If KnowledgeDecision is not present, preserve existing behavior.
        if self.knowledge_source_registry is not None:
            source = self.knowledge_source_registry.get(task.input.get("source"))
            return self._execute_retrieval_source(source, task)

        if self.retrieval is None:
            return ExecutionResult(success=False, error="Retrieval capability unavailable")

        if top_k is not None and (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k <= 0
        ):
            return ExecutionResult(success=False, error="Retrieval top_k must be a positive integer")

        if hasattr(self.retrieval, "retrieve"):
            retrieved = self.retrieval.retrieve(query, k=top_k) if top_k is not None else self.retrieval.retrieve(query)
            if not retrieved:
                return ExecutionResult(success=False, output={"query": query, "results": [], "context_found": False}, error="No sufficiently relevant retrieval context found", metadata={"capability": "retrieval"})
            result = {"query": query, "results": retrieved, "context_found": True}
            return ExecutionResult(success=True, output=result, metadata={"capability": "retrieval"})

        result = self.retrieval.ask(query)
        return ExecutionResult(success=True, output=result)

    def _execute_retrieval_source(
        self,
        source,
        task: Task,
    ) -> ExecutionResult:

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

        retrieved = (
            source.retrieve(query, k=top_k)
            if top_k is not None
            else source.retrieve(query)
        )

        if not retrieved:
            return ExecutionResult(
                success=False,
                output={
                    "query": query,
                    "results": [],
                    "context_found": False,
                    "source": source.name,
                },
                error="No sufficiently relevant retrieval context found",
                metadata={"capability": "retrieval", "source": source.name},
            )

        output = {
            "query": query,
            "results": retrieved,
            "context_found": True,
            "source": source.name,
        }

        if hasattr(source, "normalize"):
            output["evidence"] = source.normalize(retrieved)

        return ExecutionResult(
            success=True,
            output=output,
            metadata={"capability": "retrieval", "source": source.name},
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
        conversation_history=None,
    ) -> ExecutionResult:

        if self.model_gateway is None:

            return ExecutionResult(
                success=False,
                error="Model capability unavailable",
            )

        query = task.input["query"]
        conversation_history = conversation_history or []

        previous_conversation = "\n".join(
            f"User: {turn['query']}\nAssistant: {turn['response']}"
            for turn in conversation_history
        ) or "No previous conversation context."

        prompt = f"""
{query}

Previous conversation context:
{previous_conversation}
""".strip()

        result = self.model_gateway.generate(
            prompt
        )

        return ExecutionResult(
            success=True,
            output=result,
        )
