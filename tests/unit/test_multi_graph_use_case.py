import pytest

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.decision import KnowledgeDecision
from core.knowledge.multi_graph import execute_multi_graph_request
from apps.fraud.composition import build_fraud_investigation_graphs, create_fraud_investigation_request
from apps.fraud.graph_correlation import (
    correlate_investigation_graph_results,
    process_investigation_graph_results,
)


def test_customer_graph_registration():
    registry = build_fraud_investigation_graphs()
    customer = registry.get("customer_graph")
    assert customer.name == "customer_graph"


def test_fraud_graph_registration():
    registry = build_fraud_investigation_graphs()
    fraud = registry.get("fraud_graph")
    assert fraud.name == "fraud_graph"


def test_synthetic_data_relationships():
    registry = build_fraud_investigation_graphs()
    customer = registry.get("customer_graph")
    fraud = registry.get("fraud_graph")

    assert customer.get_neighbors("C1001", direction="outgoing")
    assert fraud.get_neighbors("C1001", direction="outgoing")
    assert any(entry["node"]["id"] == "D500" for entry in customer.get_neighbors("C1001", direction="outgoing"))
    assert any(entry["node"]["id"] == "D500" for entry in fraud.get_neighbors("C1001", direction="outgoing"))
    assert any(entry["node"]["id"] == "C2001" for entry in customer.get_neighbors("D500", direction="incoming"))
    assert any(entry["node"]["id"] == "C2001" for entry in fraud.get_neighbors("D500", direction="incoming"))


def test_multi_graph_request_validation():
    request = create_fraud_investigation_request("Investigate customer C1001")
    assert len(request.requests) == 4
    assert request.requests[0].graph_name == "customer_graph"
    assert request.requests[1].graph_name == "fraud_graph"
    assert request.requests[0].parameters["node_id"] == "C1001"
    assert request.requests[1].parameters["node_id"] == "C1001"


def test_knowledge_decision_supports_multi_graph_requests():
    decision = KnowledgeDecision(knowledge_graph_registry=build_fraud_investigation_graphs())
    request = decision.create_request(
        "Investigate customer C1001",
        graph_requests=[{"graph_name": "customer_graph", "operation": "get_neighbors", "parameters": {"node_id": "C1001", "direction": "outgoing"}}],
    )
    assert request.kind == "graph"
    assert request.source == "multi_graph"
    assert request.graph_requests[0]["graph_name"] == "customer_graph"


def test_execution_manager_multi_graph_request_executes_both_graphs():
    registry = build_fraud_investigation_graphs()
    manager = ExecutionManager(
        knowledge_graph_registry=registry,
        graph_result_processor=process_investigation_graph_results,
    )
    request = create_fraud_investigation_request("Investigate customer C1001 and identify associated accounts, fraud cases, and devices.")
    task = Task(
        id="multi-graph-1",
        description="multi graph lookup",
        input={
            "query": "Investigate customer C1001 and identify associated accounts, fraud cases, and devices.",
            "customer_id": "C1001",
            "graph_requests": request.as_dict_list(),
        },
        metadata={"capability": "retrieval"},
    )

    result = manager.execute(task, AgentContext(request_id="req-1"))

    assert result.success is True
    assert result.output["source"] == "multi_graph"
    assert result.output["summary"]["customer_id"] == "C1001"
    assert result.output["summary"]["account_ids"] == ["A100", "A101"]
    assert result.output["summary"]["case_ids"] == ["F900"]
    assert result.output["summary"]["device_ids"] == ["D500"]
    assert result.output["summary"]["related_customers"] == ["C2001"]
    assert any("C1001 owns accounts A100, A101" in fact for fact in result.output["facts"])
    assert any("Device D500 is also associated with customer C2001" in fact for fact in result.output["facts"])
    assert result.output["evidence"].sources() == ["customer_graph", "fraud_graph"]


def test_cross_graph_correlation_uses_explicit_identifiers_only():
    registry = build_fraud_investigation_graphs()
    request = create_fraud_investigation_request("Investigate customer C1001")
    result = execute_multi_graph_request(registry, request)
    correlation = correlate_investigation_graph_results(result["results"], customer_id="C1001")

    assert correlation["summary"]["related_customers"] == ["C2001"]
    assert "Customer C1001 owns accounts A100, A101." in correlation["facts"]
    assert all("Alice" not in fact for fact in correlation["facts"])
    assert "summary" not in result
    assert "facts" not in result


def test_generic_multi_graph_execution_returns_schema_neutral_results_and_evidence():
    registry = build_fraud_investigation_graphs()
    request = create_fraud_investigation_request("Investigate customer C1001")

    result = execute_multi_graph_request(registry, request)

    assert result["results"]
    assert result["evidence"].sources() == ["customer_graph", "fraud_graph"]
    assert not {"customer_id", "account_ids", "case_ids", "device_ids", "facts"} & set(result)


def test_missing_graph_controlled_failure():
    registry = build_fraud_investigation_graphs()
    request = [{"graph_name": "missing_graph", "operation": "get_neighbors", "parameters": {"node_id": "C1001"}}]
    with pytest.raises(ValueError, match="Required graph 'missing_graph' unavailable"):
        execute_multi_graph_request(registry, request)


def test_graph_failure_controlled_failure():
    registry = build_fraud_investigation_graphs()

    class ExplodingGraph:
        name = "customer_graph"

        def get_neighbors(self, node_id, direction="outgoing"):
            raise RuntimeError("synthetic graph failure")

    registry._graphs["customer_graph"] = ExplodingGraph()
    request = [{"graph_name": "customer_graph", "operation": "get_neighbors", "parameters": {"node_id": "C1001"}}]
    with pytest.raises(ValueError, match="synthetic graph failure"):
        execute_multi_graph_request(registry, request)
