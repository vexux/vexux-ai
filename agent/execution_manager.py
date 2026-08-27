from typing import Any
import traceback

from core.contracts.evidence import Evidence, EvidenceSet
from core.knowledge.multi_graph import execute_multi_graph_request

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
                    task,
                    context,
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
        context: AgentContext | None = None,
    ) -> ExecutionResult:

        # Use the KnowledgeDecision component (if available) to normalize and
        # validate what kind of knowledge operation the task requests.
        query = task.input.get("query")
        explicit_source = task.input.get("source")
        top_k = task.input.get("top_k")
        graph_requests = task.input.get("graph_requests") or task.input.get("multi_graph_requests") or task.input.get("requests")

        if not isinstance(query, str) or not query.strip():
            return ExecutionResult(success=False, error="Retrieval task missing 'query' field")

        # Multi-graph requests are intentionally handled before the default
        # source-routing logic. This preserves controlled failure semantics:
        # missing or failing graphs are surfaced instead of silently falling back.
        if graph_requests:
            # Authorize each requested graph before any execution. Authorization must
            # occur prior to submitting protected tasks for parallel execution.
            if self.policy is not None:
                from core.contracts.audit import make_event
                from core.audit_logger import emit as emit_audit
                # emit request_started for this multi-graph retrieval (use task.id as request id)
                try:
                    evt_start = make_event(event_type="request_started", request_id=task.id, status="started", metadata={"kind": "multi_graph"})
                    emit_audit(evt_start)
                except Exception:
                    pass

                for item in graph_requests:
                    name = item.get("graph_name") or item.get("source")
                    try:
                        decision = self.policy.authorize_resource(context.user_id if context is not None else None, "knowledge_graph", name, "read", {"task_id": task.id})
                    except Exception as exc:
                        import traceback as _tb
                        tb = _tb.format_exc()
                        # emit authorization error event
                        try:
                            evt = make_event(event_type="authorization_denied", request_id=task.id, task_id=None, resource_type="knowledge_graph", resource_name=name, action="read", status="error", metadata={"error": str(exc)})
                            emit_audit(evt)
                        except Exception:
                            pass
                        return ExecutionResult(success=False, error=f"Authorization error: {exc}", metadata={"trace": tb})
                    # emit authorization allowed/denied
                    try:
                        if decision.allowed:
                            evt = make_event(event_type="authorization_allowed", request_id=task.id, resource_type="knowledge_graph", resource_name=name, action="read", status="allowed", metadata={"policy": decision.policy_name})
                        else:
                            evt = make_event(event_type="authorization_denied", request_id=task.id, resource_type="knowledge_graph", resource_name=name, action="read", status="denied", metadata={"policy": decision.policy_name, "reason": decision.reason})
                        emit_audit(evt)
                    except Exception:
                        pass
                    if not decision.allowed:
                        return ExecutionResult(success=False, error=f"Unauthorized access to knowledge graph: {name}", metadata={"policy": decision.policy_name, "reason": decision.reason})
            try:
                result = self._execute_multi_graph_request(task, graph_requests)
                # emit request_completed
                try:
                    from core.contracts.audit import make_event as _make_event
                    from core.audit_logger import emit as _emit_audit
                    evt_c = _make_event(event_type="request_completed", request_id=task.id, status="completed", metadata={"kind": "multi_graph"})
                    _emit_audit(evt_c)
                except Exception:
                    pass
                return result
            except Exception as exc:
                # emit request_failed
                try:
                    from core.contracts.audit import make_event as _make_event
                    from core.audit_logger import emit as _emit_audit
                    evt_fail = _make_event(event_type="request_completed", request_id=task.id, status="failed", metadata={"error": str(exc), "kind": "multi_graph"})
                    _emit_audit(evt_fail)
                except Exception:
                    pass
                return ExecutionResult(success=False, error=str(exc))

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
                # Allow callers to specify a high-level operation and structured params in the task input.
                operation = task.input.get("operation")
                params = dict(task.input.get("params", {})) if isinstance(task.input.get("params"), dict) else {}
                if top_k is not None:
                    params.setdefault("top_k", top_k)

                kr = self.knowledge_decision.create_request(
                    query=query,
                    explicit_source=explicit_source,
                    operation=operation,
                    params=params,
                    graph_requests=graph_requests,
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
                # Execute graph operations using the configured KnowledgeGraphRegistry.
                if self.knowledge_graph_registry is None:
                    return ExecutionResult(success=False, error="Knowledge graph capability unavailable")

                if kr.source == "multi_graph":
                    return self._execute_multi_graph_request(task, kr.graph_requests or task.input.get("graph_requests", []))

                try:
                    graph = self.knowledge_graph_registry.get(kr.source)
                except Exception as exc:
                    return ExecutionResult(success=False, error=str(exc))

                # Authorize access to the resolved graph resource
                if self.policy is not None:
                    try:
                        decision = self.policy.authorize_resource(context.user_id if context is not None else None, "knowledge_graph", graph.name if hasattr(graph, "name") else kr.source, "read", {"task_id": task.id})
                    except Exception as exc:
                        return ExecutionResult(success=False, error=f"Authorization error: {exc}")
                    if not decision.allowed:
                        return ExecutionResult(success=False, error=f"Unauthorized access to knowledge graph: {graph.name}", metadata={"policy": decision.policy_name, "reason": decision.reason})

                operation = kr.operation or kr.params.get("operation") if hasattr(kr, "params") else kr.operation
                params = kr.params if hasattr(kr, "params") else {}

                try:
                    # Node lookup
                    if operation in ("get_node", "node_lookup", "node"):
                        node_id = params.get("node_id") or params.get("id")
                        if not node_id:
                            return ExecutionResult(success=False, error="Graph operation 'get_node' requires 'node_id' parameter")
                        node = graph.get_node(node_id)
                        evidence = EvidenceSet()
                        evidence.add(Evidence(graph.name, str(node), "graph_node", metadata={"id": node_id}))
                        output = {"query": query, "result": node, "context_found": True, "source": graph.name, "evidence": evidence}
                        return ExecutionResult(success=True, output=output, metadata={"capability": "retrieval", "source": graph.name})

                    # Relationship lookup
                    if operation in ("get_relationship", "relationship_lookup", "relationship"):
                        rel_id = params.get("rel_id") or params.get("id")
                        if not rel_id:
                            return ExecutionResult(success=False, error="Graph operation 'get_relationship' requires 'rel_id' parameter")
                        rel = graph.get_relationship(rel_id)
                        evidence = EvidenceSet()
                        evidence.add(Evidence(graph.name, str(rel), "graph_relationship", metadata={"id": rel_id}))
                        output = {"query": query, "result": rel, "context_found": True, "source": graph.name, "evidence": evidence}
                        return ExecutionResult(success=True, output=output, metadata={"capability": "retrieval", "source": graph.name})

                    # Neighbor traversal
                    if operation in ("get_neighbors", "neighbors", "neighbor_traversal"):
                        node_id = params.get("node_id") or params.get("id")
                        direction = params.get("direction", "outgoing")
                        if not node_id:
                            return ExecutionResult(success=False, error="Graph operation 'get_neighbors' requires 'node_id' parameter")
                        neighbors = graph.get_neighbors(node_id, direction=direction)
                        evidence = EvidenceSet()
                        for item in neighbors:
                            evidence.add(Evidence(graph.name, str(item), "graph_neighbor", metadata={"node_id": node_id, "direction": item.get("direction")}))
                        output = {"query": query, "results": neighbors, "context_found": bool(neighbors), "source": graph.name, "evidence": evidence}
                        return ExecutionResult(success=True, output=output, metadata={"capability": "retrieval", "source": graph.name})

                    return ExecutionResult(success=False, error=f"Unsupported graph operation: {operation}")

                except Exception as exc:
                    return ExecutionResult(success=False, error=str(exc))

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

    def _execute_multi_graph_request(self, task: Task, graph_requests):
        if self.knowledge_graph_registry is None:
            raise ValueError("Knowledge graph capability unavailable")

        if not isinstance(graph_requests, list) or not graph_requests:
            raise ValueError("Multi-graph request requires a non-empty 'graph_requests' list")

        requests = []
        for item in graph_requests:
            if isinstance(item, dict):
                request = dict(item)
            else:
                request = item.as_dict() if hasattr(item, "as_dict") else dict(item)
            if not request.get("graph_name") and request.get("source"):
                request["graph_name"] = request.get("source")
            if not request.get("operation") and request.get("params"):
                request["operation"] = request.get("params", {}).get("operation")
            if not request.get("parameters") and request.get("params"):
                request["parameters"] = request.get("params")
            requests.append(request)

        customer_id = task.input.get("customer_id")
        try:
            result = execute_multi_graph_request(self.knowledge_graph_registry, requests, customer_id=customer_id)
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        evidence = result.get("evidence")
        output = {
            "query": task.input.get("query"),
            "results": result.get("results", []),
            "context_found": result.get("context_found", bool(result.get("results"))),
            "source": "multi_graph",
            "evidence": evidence,
            "summary": result.get("summary", {}),
            "facts": result.get("facts", []),
        }
        return ExecutionResult(success=True, output=output, metadata={"capability": "retrieval", "source": "multi_graph"})

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

        # Authorize access to this knowledge source before retrieval
        if self.policy is not None:
            from core.contracts.audit import make_event
            from core.audit_logger import emit as emit_audit
            try:
                decision = self.policy.authorize_resource(None, "knowledge_source", getattr(source, "name", None), "read", {"task_id": task.id})
            except Exception as exc:
                try:
                    evt = make_event(event_type="authorization_denied", request_id=task.id, resource_type="knowledge_source", resource_name=getattr(source, "name", None), action="read", status="error", metadata={"error": str(exc)})
                    emit_audit(evt)
                except Exception:
                    pass
                return ExecutionResult(success=False, error=f"Authorization error: {exc}", metadata={})
            try:
                if decision.allowed:
                    evt = make_event(event_type="authorization_allowed", request_id=task.id, resource_type="knowledge_source", resource_name=getattr(source, "name", None), action="read", status="allowed", metadata={"policy": decision.policy_name})
                else:
                    evt = make_event(event_type="authorization_denied", request_id=task.id, resource_type="knowledge_source", resource_name=getattr(source, "name", None), action="read", status="denied", metadata={"policy": decision.policy_name, "reason": decision.reason})
                emit_audit(evt)
            except Exception:
                pass
            if not decision.allowed:
                return ExecutionResult(success=False, error=f"Unauthorized access to knowledge source: {getattr(source, 'name', None)}", metadata={"policy": decision.policy_name, "reason": decision.reason})

        # emit resource_accessed (start)
        try:
            from core.contracts.audit import make_event as _make_event
            from core.audit_logger import emit as _emit_audit
            evt_start = _make_event(event_type="resource_accessed", request_id=task.id, resource_type="knowledge_source", resource_name=getattr(source, "name", None), action="read", status="started")
            _emit_audit(evt_start)
        except Exception:
            pass

        parameters = task.input.get("parameters")
        if parameters is not None:
            retrieved = source.retrieve(query, k=top_k, parameters=parameters)
        elif top_k is not None:
            retrieved = source.retrieve(query, k=top_k)
        else:
            retrieved = source.retrieve(query)

        # emit resource_accessed (completed)
        try:
            from core.contracts.audit import make_event as _make_event
            from core.audit_logger import emit as _emit_audit
            evt_done = _make_event(event_type="resource_accessed", request_id=task.id, resource_type="knowledge_source", resource_name=getattr(source, "name", None), action="read", status="completed")
            _emit_audit(evt_done)
        except Exception:
            pass

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
