from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

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


class GraphCorrelator:
    def correlate(self, results: Iterable[Dict[str, Any]], customer_id: Optional[str] = None) -> Dict[str, Any]:
        return correlate_graph_results(results, customer_id=customer_id)


CrossGraphAggregator = GraphCorrelator


def normalize_graph_results(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append(item)
    return normalized


def _flatten_graph_items(result: Any) -> List[Dict[str, Any]]:
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _extract_identifier(node: Any, identifier_key: str) -> Optional[str]:
    if not isinstance(node, dict):
        return None

    properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    value = properties.get(identifier_key)
    if value is not None:
        return str(value)
    if identifier_key in node:
        return str(node[identifier_key])
    return None


def correlate_graph_results(results: Iterable[Dict[str, Any]], customer_id: Optional[str] = None) -> Dict[str, Any]:
    normalized = normalize_graph_results(results)
    account_ids = set()
    case_ids = set()
    device_ids = set()
    related_customers = set()
    observed_customer_ids = set()
    evidence_items: List[Evidence] = []

    for result in normalized:
        graph_name = result.get("graph_name") or result.get("source") or "unknown_graph"
        payload = result.get("result")
        for item in _flatten_graph_items(payload):
            if "node" in item and isinstance(item["node"], dict):
                node = item["node"]
            elif "relationship" in item and isinstance(item["relationship"], dict):
                node = item["relationship"]
            else:
                node = item

            if not isinstance(node, dict):
                continue

            account_id = _extract_identifier(node, "account_id")
            case_id = _extract_identifier(node, "case_id")
            device_id = _extract_identifier(node, "device_id")
            customer = _extract_identifier(node, "customer_id")
            if customer:
                observed_customer_ids.add(customer)
            if account_id:
                account_ids.add(account_id)
            if case_id:
                case_ids.add(case_id)
            if device_id:
                device_ids.add(device_id)

            if customer and customer != customer_id and customer_id:
                related_customers.add(customer)

            evidence_items.append(Evidence(graph_name, str(node), "graph_result", metadata={"graph_name": graph_name}))

    if customer_id is None:
        customer_id = next(iter(sorted(observed_customer_ids)), None)

    account_list = sorted(account_ids)
    case_list = sorted(case_ids)
    device_list = sorted(device_ids)
    related_customers_list = sorted(related_customers)

    facts: List[str] = []
    if customer_id and account_list:
        facts.append(f"Customer {customer_id} owns accounts {', '.join(account_list)}.")
    if customer_id and case_list:
        facts.append(f"The fraud graph associates {customer_id} with case {', '.join(case_list)}.")
    if device_list:
        if customer_id and device_list:
            facts.append(f"Customer {customer_id} is associated with device {', '.join(device_list)}.")
        if related_customers_list:
            facts.append(f"Device {', '.join(device_list)} is also associated with customer {', '.join(related_customers_list)}.")

    evidence = EvidenceSet()
    for item in evidence_items:
        evidence.add(item)

    return {
        "customer_id": customer_id,
        "account_ids": account_list,
        "case_ids": case_list,
        "device_ids": device_list,
        "related_customers": related_customers_list,
        "facts": facts,
        "evidence": evidence,
    }


def execute_multi_graph_request(
    registry: KnowledgeGraphRegistry,
    request: MultiGraphRequest | List[Dict[str, Any]],
    customer_id: Optional[str] = None,
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
        summary = correlate_graph_results(results, customer_id=customer_id)
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
    evidence = summary["evidence"]
    output = {
        "query": query,
        "results": results,
        "context_found": bool(results),
        "source": "multi_graph",
        "evidence": evidence,
        "summary": {
            "customer_id": summary["customer_id"],
            "account_ids": summary["account_ids"],
            "case_ids": summary["case_ids"],
            "device_ids": summary["device_ids"],
            "related_customers": summary["related_customers"],
        },
        "facts": summary["facts"],
    }
    return output
