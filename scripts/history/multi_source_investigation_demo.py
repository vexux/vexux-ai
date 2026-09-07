"""End-to-end heterogeneous graph and SQLite investigation demonstration."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from apps.fraud.composition import build_fraud_investigation_graphs
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "business.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                """
                CREATE TABLE accounts (account_id TEXT, customer_id TEXT, account_type TEXT, status TEXT);
                INSERT INTO accounts VALUES ('A100', 'C1001', 'checking', 'active');
                INSERT INTO accounts VALUES ('A101', 'C1001', 'savings', 'active');
                """
            )
        finally:
            connection.close()

        sources = KnowledgeSourceRegistry()
        sql = SQLKnowledgeSource(SQLiteBackend(str(database)))
        sql.name = "business_db"
        sources.register(sql)
        graphs = KnowledgeGraphRegistry()
        fraud_graph = build_fraud_investigation_graphs().get("fraud_graph")
        graphs.register(fraud_graph)
        manager = ExecutionManager(
            knowledge_graph_registry=graphs,
            knowledge_source_registry=sources,
        )
        customer_graph = None
        customer_nodes = []
        customer_relationships = []
        if os.getenv("NEO4J_URI"):
            customer_graph = Neo4jKnowledgeGraph(
                os.environ["NEO4J_URI"],
                os.environ.get("NEO4J_USERNAME", ""),
                os.environ.get("NEO4J_PASSWORD", ""),
                name="customer_graph",
                database=os.getenv("NEO4J_DATABASE"),
            )
            graphs.register(customer_graph)
            for node_id, label, properties in [
                ("C1001", "Customer", {"customer_id": "C1001", "name": "Alice Smith"}),
                ("C2001", "Customer", {"customer_id": "C2001", "name": "Bob Jones"}),
                ("A100", "Account", {"account_id": "A100", "type": "checking", "status": "active"}),
                ("A101", "Account", {"account_id": "A101", "type": "savings", "status": "active"}),
                ("D500", "Device", {"device_id": "D500", "type": "mobile", "platform": "Android"}),
            ]:
                customer_graph.add_node(node_id, label=label, properties=properties)
                customer_nodes.append(node_id)
            for source, target, rel_type in [
                ("C1001", "A100", "owns"),
                ("C1001", "A101", "owns"),
                ("C1001", "D500", "uses"),
                ("C2001", "D500", "uses"),
            ]:
                customer_relationships.append(
                    customer_graph.add_relationship(source, target, rel_type=rel_type)["id"]
                )
            graph_requests = [
                {"graph_name": "customer_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
                {"graph_name": "fraud_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
            ]
            print("customer_graph backend = Neo4j")
        else:
            graph_requests = [
                {"graph_name": "fraud_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
            ]
            print("customer_graph backend = unavailable (Neo4j is not configured)")
        print("fraud_graph backend = InMemory")
        print("business_db backend = SQLite")
        print("request = available graph sources + business_db for customer C1001")
        graph_result = manager.execute(
            Task(
                id="graphs",
                description="Read graph relationships",
                input={"query": "C1001 relationships", "customer_id": "C1001", "graph_requests": graph_requests},
                metadata={"capability": "retrieval"},
            ),
            AgentContext(request_id="multi-source-demo", user_id="investigator"),
        )
        sql_result = manager.execute(
            Task(
                id="business-db",
                description="Read account details",
                input={
                    "query": "SELECT account_id, account_type, status FROM accounts WHERE customer_id = ?",
                    "parameters": ("C1001",),
                    "source": "business_db",
                },
                metadata={"capability": "retrieval"},
            ),
            AgentContext(request_id="multi-source-demo", user_id="investigator"),
        )
        print("authorization = allowed for configured sources")
        print(f"retrieval status = graphs:{graph_result.success}, business_db:{sql_result.success}")
        if graph_result.success and sql_result.success:
            evidence = graph_result.output["evidence"].items + sql_result.output["evidence"].items
            print(f"evidence sources = {[item.source for item in evidence]}")
            label = "final result" if customer_graph else "partial result"
            print(f"{label} = accounts {sql_result.output['results']}; graph facts {graph_result.output['facts']}")
        else:
            print(f"final result = unavailable ({graph_result.error or sql_result.error})")
        if customer_graph:
            for relationship_id in customer_relationships:
                customer_graph.remove_relationship(relationship_id)
            for node_id in customer_nodes:
                customer_graph.remove_node(node_id)


if __name__ == "__main__":
    main()
