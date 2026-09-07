from core.contracts.execution import AgentContext, Task
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.policy.default import DefaultPolicy, PolicyDecision
from agent.execution_manager import ExecutionManager


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def single(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, nodes, relationships):
        self.nodes = nodes
        self.relationships = relationships

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query, **params):
        if "RETURN n" in query:
            node = self.nodes.get(params["node_id"])
            return FakeResult([{"n": node}] if node else [])
        if "RETURN source, node, r" in query:
            node_id = params["node_id"]
            rows = []
            for relationship in self.relationships.values():
                if relationship["source"] == node_id:
                    rows.append({
                        "source": self.nodes[relationship["source"]],
                        "node": self.nodes[relationship["target"]],
                        "r": relationship,
                    })
            return FakeResult(rows)
        if "RETURN source, target, r" in query:
            relationship = self.relationships[params["rel_id"]]
            return FakeResult([{
                "source": self.nodes[relationship["source"]],
                "target": self.nodes[relationship["target"]],
                "r": relationship,
            }])
        return FakeResult([])


class FakeDriver:
    def __init__(self, nodes, relationships):
        self.session_instance = FakeSession(nodes, relationships)

    def session(self, **kwargs):
        return self.session_instance


class SelectivePolicy(DefaultPolicy):
    def __init__(self, denied=None):
        super().__init__()
        self.denied = set(denied or ())

    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if resource_name in self.denied:
            return PolicyDecision(False, f"{resource_name} denied", "test")
        return PolicyDecision(True)


def build_registry():
    customer_nodes = {
        "C1001": {"id": "C1001", "label": "Customer", "properties": {"customer_id": "C1001", "name": "Alice Smith"}},
        "A100": {"id": "A100", "label": "Account", "properties": {"account_id": "A100", "type": "checking", "status": "active"}},
        "A101": {"id": "A101", "label": "Account", "properties": {"account_id": "A101", "type": "savings", "status": "active"}},
        "D500": {"id": "D500", "label": "Device", "properties": {"device_id": "D500", "type": "mobile", "platform": "Android"}},
    }
    customer_relationships = {
        "owns-100": {"id": "owns-100", "source": "C1001", "target": "A100", "type": "owns", "properties": {}},
        "owns-101": {"id": "owns-101", "source": "C1001", "target": "A101", "type": "owns", "properties": {}},
        "uses-500": {"id": "uses-500", "source": "C1001", "target": "D500", "type": "uses", "properties": {}},
    }
    registry = KnowledgeGraphRegistry()
    registry.register(Neo4jKnowledgeGraph(
        "bolt://mock", "neo4j", "password", name="customer_graph",
        driver=FakeDriver(customer_nodes, customer_relationships),
    ))

    fraud = InMemoryKnowledgeGraph()
    fraud.name = "fraud_graph"
    for node_id, label, properties in [
        ("C1001", "Customer", {"customer_id": "C1001"}),
        ("C2001", "Customer", {"customer_id": "C2001"}),
        ("F900", "FraudCase", {"case_id": "F900", "type": "suspicious-device-investigation", "status": "open"}),
        ("D500", "Device", {"device_id": "D500"}),
    ]:
        fraud.add_node(node_id, label=label, properties=properties)
    fraud.add_relationship("C1001", "F900", "involved_in")
    fraud.add_relationship("C1001", "D500", "linked_to")
    fraud.add_relationship("C2001", "D500", "linked_to")
    registry.register(fraud)
    return registry


def test_heterogeneous_backends_execute_and_aggregate_with_evidence():
    registry = build_registry()
    assert registry.get("customer_graph").__class__ is Neo4jKnowledgeGraph
    assert registry.get("fraud_graph").__class__ is InMemoryKnowledgeGraph
    manager = ExecutionManager(knowledge_graph_registry=registry, policy=SelectivePolicy())
    task = Task(
        id="heterogeneous",
        description="investigate",
        input={
            "query": "C1001 relationships",
            "customer_id": "C1001",
            "graph_requests": [
                {"graph_name": "customer_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
                {"graph_name": "fraud_graph", "operation": "get_neighbors", "params": {"node_id": "C1001"}},
            ],
        },
        metadata={"capability": "retrieval"},
    )
    result = manager.execute(task, AgentContext(request_id="heterogeneous-request", user_id="investigator"))
    assert result.success is True
    assert result.output["summary"]["account_ids"] == ["A100", "A101"]
    assert result.output["summary"]["case_ids"] == ["F900"]
    assert result.output["summary"]["device_ids"] == ["D500"]
    assert {item.source for item in result.output["evidence"].items} == {"customer_graph", "fraud_graph"}


def test_heterogeneous_graph_authorization_denies_before_execution():
    registry = build_registry()
    manager = ExecutionManager(
        knowledge_graph_registry=registry,
        policy=SelectivePolicy({"fraud_graph"}),
    )
    task = Task(
        id="denied-heterogeneous",
        description="investigate",
        input={
            "query": "C1001 relationships",
            "graph_requests": [
                {"graph_name": "customer_graph", "operation": "get_node", "params": {"node_id": "C1001"}},
                {"graph_name": "fraud_graph", "operation": "get_node", "params": {"node_id": "C1001"}},
            ],
        },
        metadata={"capability": "retrieval"},
    )
    result = manager.execute(task, AgentContext(request_id="denied-request", user_id="support_user"))
    assert result.success is False
    assert "Unauthorized access to knowledge graph: fraud_graph" in (result.error or "")
