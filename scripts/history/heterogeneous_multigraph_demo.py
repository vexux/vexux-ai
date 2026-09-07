"""Run the Phase 33 heterogeneous multi-graph proof with an optional Neo4j."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.policy.default import DefaultPolicy


def _fraud_graph():
    graph = InMemoryKnowledgeGraph()
    graph.name = "fraud_graph"
    for node_id, label, properties in [
        ("C1001", "Customer", {"customer_id": "C1001"}),
        ("C2001", "Customer", {"customer_id": "C2001"}),
        ("F900", "FraudCase", {"case_id": "F900", "status": "open"}),
        ("D500", "Device", {"device_id": "D500"}),
    ]:
        graph.add_node(node_id, label=label, properties=properties)
    graph.add_relationship("C1001", "F900", "involved_in")
    graph.add_relationship("C1001", "D500", "linked_to")
    graph.add_relationship("C2001", "D500", "linked_to")
    return graph


def main():
    if not os.getenv("NEO4J_URI"):
        print("customer_graph backend = Neo4j (unavailable: NEO4J_URI is not configured)")
        print("fraud_graph backend = InMemory")
        return

    registry = KnowledgeGraphRegistry()
    try:
        customer_graph = Neo4jKnowledgeGraph(
            uri=os.environ["NEO4J_URI"],
            username=os.environ.get("NEO4J_USERNAME", ""),
            password=os.environ.get("NEO4J_PASSWORD", ""),
            database=os.getenv("NEO4J_DATABASE"),
            name="customer_graph",
        )
    except (RuntimeError, ValueError) as exc:
        print(f"customer_graph backend = Neo4j (unavailable: {exc})")
        print("fraud_graph backend = InMemory")
        return
    fraud_graph = _fraud_graph()
    customer_node_ids = []
    customer_relationship_ids = []
    try:
        registry.register(customer_graph)
        registry.register(fraud_graph)
        for node_id, label, properties in [
            ("C1001", "Customer", {"customer_id": "C1001", "name": "Alice Smith"}),
            ("C2001", "Customer", {"customer_id": "C2001", "name": "Bob Jones"}),
            ("A100", "Account", {"account_id": "A100", "type": "checking", "status": "active"}),
            ("A101", "Account", {"account_id": "A101", "type": "savings", "status": "active"}),
            ("D500", "Device", {"device_id": "D500", "type": "mobile", "platform": "Android"}),
        ]:
            customer_graph.add_node(node_id, label=label, properties=properties)
            customer_node_ids.append(node_id)
        for source, target, rel_type in [
            ("C1001", "A100", "owns"),
            ("C1001", "A101", "owns"),
            ("C1001", "D500", "uses"),
            ("C2001", "D500", "uses"),
        ]:
            customer_relationship_ids.append(
                customer_graph.add_relationship(source, target, rel_type=rel_type)["id"]
            )

        request_specs = [
            {"graph_name": "customer_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
            {"graph_name": "fraud_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
        ]
        print("customer_graph backend = Neo4j")
        print("fraud_graph backend = InMemory")
        print(f"graph request = {request_specs}")
        print("authorization = allowed for customer_graph, fraud_graph")
        result = ExecutionManager(
            knowledge_graph_registry=registry,
            policy=DefaultPolicy(),
        ).execute(
            Task(
                id="heterogeneous-demo",
                description="Investigate C1001",
                input={"query": "C1001 relationships", "customer_id": "C1001", "graph_requests": request_specs},
                metadata={"capability": "retrieval"},
            ),
            AgentContext(request_id="heterogeneous-demo", user_id="investigator"),
        )
        print(f"retrieval status = {'success' if result.success else 'failed'}")
        if result.success:
            print(f"aggregated relationships = {result.output['facts']}")
            print(f"final result = {result.output['summary']}")
        else:
            print(f"final result = unavailable ({result.error})")
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"Neo4j heterogeneous investigation unavailable ({exc})")
    finally:
        for relationship_id in customer_relationship_ids:
            customer_graph.remove_relationship(relationship_id)
        for node_id in customer_node_ids:
            customer_graph.remove_node(node_id)


if __name__ == "__main__":
    main()
