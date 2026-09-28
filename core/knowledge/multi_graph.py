from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from core.contracts.evidence import Evidence, EvidenceSet
from core.knowledge.graph_registry import KnowledgeGraphRegistry


@dataclass(frozen=True)
class GraphRequest:
    graph_name: str
    operation: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "graph_name": self.graph_name,
            "operation": self.operation,
            "parameters": dict(self.parameters),
        }


@dataclass
class MultiGraphRequest:
    query: str
    requests: List[GraphRequest] = field(default_factory=list)

    def as_dict_list(self) -> List[Dict[str, Any]]:
        return [request.as_dict() for request in self.requests]



def execute_graph_request(graph: Any, request: Dict[str, Any] | GraphRequest) -> Dict[str, Any]:
    if isinstance(request, GraphRequest):
        request_dict = request.as_dict()
    else:
        request_dict = dict(request)

    graph_name = request_dict.get("graph_name") or request_dict.get("source")
    operation = request_dict.get("operation")
    params = request_dict.get("parameters") or {}

    if graph_name is not None and graph.name != graph_name:
        raise ValueError(f"Graph mismatch: expected {graph_name} but got {graph.name}")

    if operation in ("get_node", "node_lookup", "node"):
        node_id = params.get("node_id") or params.get("id")
        result = graph.get_node(node_id)
    elif operation in ("get_relationship", "relationship_lookup", "relationship"):
        rel_id = params.get("rel_id") or params.get("id")
        result = graph.get_relationship(rel_id)
    elif operation in ("get_neighbors", "neighbors", "neighbor_traversal"):
        node_id = params.get("node_id") or params.get("id")
        direction = params.get("direction", "outgoing")
        result = graph.get_neighbors(node_id, direction=direction)
    else:
        raise ValueError(f"Unsupported graph operation: {operation}")

    return {
        "graph_name": graph.name,
        "operation": operation,
        "parameters": params,
        "result": result,
        "source": graph.name,
        "context_found": True,
    }


def _flatten_graph_items(result: Any) -> List[Dict[str, Any]]:
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _build_graph_evidence(results: Iterable[Dict[str, Any]]) -> EvidenceSet:
    evidence_items: List[Evidence] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        graph_name = result.get("graph_name") or result.get("source") or "unknown_graph"
        payload = result.get("result")
        for item in _flatten_graph_items(payload):
            if "node" in item and isinstance(item["node"], dict):
                node = item["node"]
            elif "relationship" in item and isinstance(item["relationship"], dict):
                node = item["relationship"]
            else:
                node = item
            evidence_items.append(
                Evidence(graph_name, str(node), "graph_result", metadata={"graph_name": graph_name})
            )
    evidence = EvidenceSet()
    for item in evidence_items:
        evidence.add(item)
    return evidence


def execute_multi_graph_request(
    registry: KnowledgeGraphRegistry,
    request: MultiGraphRequest | List[Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(request, MultiGraphRequest):
        requests = request.requests
        query = request.query
    else:
        requests = [
            GraphRequest(
                graph_name=item.get("graph_name"),
                operation=item.get("operation"),
                parameters=item.get("parameters", {}),
            )
            for item in request
        ]
        query = ""

    if not requests:
        raise ValueError("Multi-graph request requires at least one graph request")

    results: List[Dict[str, Any]] = []
    from core.audit_logger import emit as emit_audit
    from core.contracts.audit import make_event

    with ThreadPoolExecutor(max_workers=min(len(requests), 4)) as executor:
        future_map = {}
        # record start times per future so durations can be reported
        start_times = {}
        for request_spec in requests:
            request_dict = request_spec.as_dict() if isinstance(request_spec, GraphRequest) else dict(request_spec)
            graph_name = request_dict.get("graph_name")
            if not graph_name:
                raise ValueError("Each graph request must include a 'graph_name'")
            try:
                graph = registry.get(graph_name)
            except Exception as exc:
                raise ValueError(f"Required graph '{graph_name}' unavailable: {exc}") from exc
            # emit task_started audit event (task id is graph_name:operation)
            op = request_dict.get("operation")
            task_id = f"{graph_name}:{op}"
            evt = make_event(
                event_type="task_started",
                request_id=None,
                session_id=None,
                orchestration_id=None,
                task_id=task_id,
                agent_name=None,
                status="started",
                resource_type="knowledge_graph",
                resource_name=graph_name,
                action=op,
                metadata={"source": "multi_graph"},
            )
            try:
                emit_audit(evt)
            except Exception:
                pass
            future = executor.submit(execute_graph_request, graph, request_dict)
            future_map[future] = request_dict
            start_times[future] = __import__("time").time()

        for future in as_completed(future_map):
            request_dict = future_map[future]
            graph_name = request_dict.get("graph_name")
            operation = request_dict.get("operation")
            task_id = f"{graph_name}:{operation}"
            try:
                result = future.result()
                results.append(result)
                # emit task_completed with duration
                duration = None
                try:
                    duration = (__import__("time").time() - start_times.get(future, 0)) * 1000.0
                except Exception:
                    duration = None
                evt = make_event(
                    event_type="task_completed",
                    request_id=None,
                    session_id=None,
                    orchestration_id=None,
                    task_id=task_id,
                    agent_name=None,
                    status="completed",
                    resource_type="knowledge_graph",
                    resource_name=graph_name,
                    action=operation,
                    duration_ms=duration,
                    metadata={"source": "multi_graph"},
                )
                try:
                    emit_audit(evt)
                except Exception:
                    pass
            except Exception as exc:
                # emit task_failed
                try:
                    duration = (__import__("time").time() - start_times.get(future, 0)) * 1000.0
                except Exception:
                    duration = None
                evt = make_event(
                    event_type="task_failed",
                    request_id=None,
                    session_id=None,
                    orchestration_id=None,
                    task_id=task_id,
                    agent_name=None,
                    status="failed",
                    resource_type="knowledge_graph",
                    resource_name=graph_name,
                    action=operation,
                    duration_ms=duration,
                    metadata={"error": str(exc), "source": "multi_graph"},
                )
                try:
                    emit_audit(evt)
                except Exception:
                    pass
                request_dict = future_map[future]
                graph_name = request_dict.get("graph_name")
                operation = request_dict.get("operation")
                raise ValueError(f"Graph '{graph_name}' operation '{operation}' failed: {exc}") from exc

        results.sort(key=lambda item: (item.get("graph_name") or "", item.get("operation") or ""))
        evidence = _build_graph_evidence(results)
        try:
            emit_audit(
                make_event(
                    event_type="resource_accessed",
                    status="aggregated",
                    resource_type="knowledge_graph",
                    resource_name="multi_graph",
                    action="aggregate",
                    metadata={
                        "source": "multi_graph",
                        "graph_count": len({item.get("graph_name") for item in results}),
                    },
                )
            )
        except Exception:
            pass
    output = {
        "query": query,
        "results": results,
        "context_found": bool(results),
        "source": "multi_graph",
        "evidence": evidence,
    }
    return output
