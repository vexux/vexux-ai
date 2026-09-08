from decimal import Decimal

import pytest

from apps.fraud.domain import Customer, InvestigationResult, Transaction
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry


class FakeSource:
    name = "business_db"
    description = "fake business source"
    capabilities = ["structured_query"]

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def retrieve(self, query, k=None, parameters=None):
        self.queries.append((query, parameters))
        if "transactions" in query:
            return self.rows["transactions"]
        if "fraud_alerts" in query:
            return self.rows["alerts"]
        return self.rows["investigations"]


def make_service(source=None):
    customer_graph = InMemoryKnowledgeGraph()
    customer_graph.name = "customer_graph"
    customer_graph.add_node("C1001", label="Customer", properties={"name": "Alice", "risk": "high"})
    customer_graph.add_node("D5001", label="Device")
    customer_graph.add_relationship("C1001", "D5001", "USES")

    fraud_graph = InMemoryKnowledgeGraph()
    fraud_graph.name = "fraud_graph"
    fraud_graph.add_node("C1001", label="Customer")
    fraud_graph.add_node("C1002", label="Customer")
    fraud_graph.add_node("D5001", label="Device")
    fraud_graph.add_relationship("C1001", "D5001", "USES")
    fraud_graph.add_relationship("C1002", "D5001", "USES")
    fraud_graph.add_relationship("C1001", "C1002", "SHARES_DEVICE_WITH")

    graphs = KnowledgeGraphRegistry()
    graphs.register(customer_graph)
    graphs.register(fraud_graph)
    sources = KnowledgeSourceRegistry()
    sources.register(source or FakeSource({
        "transactions": [
            {"transaction_id": "T1", "customer_id": "C1001", "amount": Decimal("1300"), "status": "approved"},
            {"transaction_id": "T2", "customer_id": "C1001", "amount": Decimal("1200"), "status": "approved"},
        ],
        "alerts": [
            {"alert_id": "A1", "customer_id": "C1001", "alert_type": "velocity", "severity": "high", "status": "open"},
        ],
        "investigations": [
            {"investigation_id": "I1", "customer_id": "C1001", "fraud_case_id": "F1", "status": "open"},
        ],
    }))
    return FraudInvestigationService(graphs, sources, FraudPolicy()), fraud_graph


def test_domain_entity_validation_and_result_contract():
    with pytest.raises(ValueError):
        Customer("")
    with pytest.raises(ValueError):
        Transaction("T1", "C1001", -1, "approved")
    result = InvestigationResult(Customer("C1001"), risk_assessment="medium")
    assert result.as_dict()["subject"]["customer_id"] == "C1001"


def test_investigation_correlates_seeded_suspicious_signals_and_evidence():
    service, _ = make_service()

    result = service.investigate("C1001")

    assert result.subject.customer_id == "C1001"
    assert result.risk_assessment == "high"
    assert {"open_high_severity_alerts", "elevated_transaction_activity", "shared_device_relationship", "active_investigation"} <= set(result.contributing_signals)
    assert result.resources_consulted == ["customer_graph", "fraud_graph", "business_db"]
    assert {"customer_graph", "fraud_graph", "business_db"} <= set(result.supporting_evidence.sources())


def test_authorization_denies_fraud_graph_before_fraud_execution():
    service, fraud_graph = make_service()
    original = fraud_graph.get_neighbors
    calls = []

    def tracked(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    fraud_graph.get_neighbors = tracked

    with pytest.raises(PermissionError, match="fraud_graph"):
        service.investigate("C1001", actor="support_user")

    assert calls == []


def test_unknown_customer_and_source_failure_remain_visible():
    service, _ = make_service()
    with pytest.raises(KeyError, match="Node not found"):
        service.investigate("C9999")

    failing = FakeSource({"transactions": [], "alerts": [], "investigations": []})
    failing.retrieve = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("source unavailable"))
    service, _ = make_service(failing)
    with pytest.raises(RuntimeError, match="source unavailable"):
        service.investigate("C1001")
