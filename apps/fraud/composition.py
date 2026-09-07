from __future__ import annotations

from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.multi_graph import GraphRequest, MultiGraphRequest


def build_fraud_investigation_graphs() -> KnowledgeGraphRegistry:
    """Build the fraud-specific demo graph set used by the application boundary.

    This factory is intentionally kept outside the generic core package so that
    the platform remains domain-agnostic while the fraud workload owns its own
    fixtures and identifiers.
    """
    registry = KnowledgeGraphRegistry()

    customer_graph = InMemoryKnowledgeGraph()
    customer_graph.name = "customer_graph"
    customer_graph.aliases = (
        "customer",
        "customer knowledge graph",
        "customer knowledge graphs",
    )
    customer_graph.default_node_id = "C1001"

    customer_graph.add_node("C1001", label="Customer", properties={"customer_id": "C1001"})
    customer_graph.add_node("C2001", label="Customer", properties={"customer_id": "C2001"})
    customer_graph.add_node("A100", label="Account", properties={"account_id": "A100"})
    customer_graph.add_node("A101", label="Account", properties={"account_id": "A101"})
    customer_graph.add_node("D500", label="Device", properties={"device_id": "D500"})

    customer_graph.add_relationship("C1001", "A100", rel_type="owns", properties={"customer_id": "C1001", "account_id": "A100"})
    customer_graph.add_relationship("C1001", "A101", rel_type="owns", properties={"customer_id": "C1001", "account_id": "A101"})
    customer_graph.add_relationship("C1001", "D500", rel_type="uses", properties={"customer_id": "C1001", "device_id": "D500"})
    customer_graph.add_relationship("C2001", "D500", rel_type="uses", properties={"customer_id": "C2001", "device_id": "D500"})

    registry.register(customer_graph)

    fraud_graph = InMemoryKnowledgeGraph()
    fraud_graph.name = "fraud_graph"
    fraud_graph.aliases = (
        "fraud",
        "fraud knowledge graph",
        "fraud knowledge graphs",
    )
    fraud_graph.default_node_id = "C1001"

    fraud_graph.add_node("C1001", label="Customer", properties={"customer_id": "C1001"})
    fraud_graph.add_node("C2001", label="Customer", properties={"customer_id": "C2001"})
    fraud_graph.add_node("F900", label="FraudCase", properties={"case_id": "F900"})
    fraud_graph.add_node("D500", label="Device", properties={"device_id": "D500"})

    fraud_graph.add_relationship("C1001", "F900", rel_type="involved_in", properties={"customer_id": "C1001", "case_id": "F900"})
    fraud_graph.add_relationship("C1001", "D500", rel_type="linked_to", properties={"customer_id": "C1001", "device_id": "D500"})
    fraud_graph.add_relationship("C2001", "D500", rel_type="linked_to", properties={"customer_id": "C2001", "device_id": "D500"})

    registry.register(fraud_graph)
    return registry


create_customer_fraud_graphs = build_fraud_investigation_graphs
create_fraud_investigation_fixture = build_fraud_investigation_graphs


def create_fraud_investigation_request(
    query: str,
    customer_id: str = "C1001",
    device_id: str = "D500",
) -> MultiGraphRequest:
    """Create an application-scoped multi-graph request against the fraud graph set."""
    return MultiGraphRequest(
        query=query,
        requests=[
            GraphRequest("customer_graph", "get_neighbors", {"node_id": customer_id, "direction": "outgoing"}),
            GraphRequest("fraud_graph", "get_neighbors", {"node_id": customer_id, "direction": "outgoing"}),
            GraphRequest("customer_graph", "get_neighbors", {"node_id": device_id, "direction": "incoming"}),
            GraphRequest("fraud_graph", "get_neighbors", {"node_id": device_id, "direction": "incoming"}),
        ],
    )


__all__ = [
    "build_fraud_investigation_graphs",
    "create_customer_fraud_graphs",
    "create_fraud_investigation_fixture",
    "create_fraud_investigation_request",
]
