from core.policy.default import DefaultPolicy, PolicyDecision
from core.contracts.execution import Task, AgentContext
from agent.execution_manager import ExecutionManager
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph

from core.orchestrator import Orchestrator
from core.specialized_agents.registry import SpecializedAgentRegistry
from core.contracts.response import AgentResponse


class TestPolicy(DefaultPolicy):
    def __init__(self, deny_map=None):
        super().__init__()
        # deny_map: dict of resource_type -> set of resource_names to deny
        self.deny_map = deny_map or {}

    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        denied = self.deny_map.get(resource_type, set())
        if resource_name in denied:
            return PolicyDecision(False, f"Access to {resource_type}:{resource_name} denied for actor {actor}", policy_name="test")
        return PolicyDecision(True)


class DummySpecializedAgent:
    def __init__(self, name):
        self.name = name

    def run(self, request, session_id=None, user_id=None):
        return AgentResponse(success=True, output=f"{self.name}:ok")


def test_denied_graph_aborts_multi_graph_execution():
    # Setup graphs
    kr = KnowledgeGraphRegistry()
    g1 = InMemoryKnowledgeGraph()
    g1.name = "customer_graph"
    g1.add_node("n1", properties={})
    g2 = InMemoryKnowledgeGraph()
    g2.name = "fraud_graph"
    g2.add_node("n2", properties={})
    kr.register(g1)
    kr.register(g2)

    # Policy denies fraud_graph
    policy = TestPolicy(deny_map={"knowledge_graph": {"fraud_graph"}})

    em = ExecutionManager(knowledge_graph_registry=kr, policy=policy)

    task = Task(id="t1", description="multi", input={"query": "q", "graph_requests": [{"graph_name": "customer_graph", "operation": "get_node", "params": {"node_id": "n1"}}, {"graph_name": "fraud_graph", "operation": "get_node", "params": {"node_id": "n2"}}]}, metadata={"capability": "retrieval"})
    ctx = AgentContext(request_id="r1", user_id="bob")

    res = em.execute(task, ctx)
    assert res.success is False
    assert "Unauthorized access to knowledge graph" in (res.error or "")


def test_unauthorized_specialized_agent_delegation():
    policy = TestPolicy(deny_map={"specialized_agent": {"research"}})

    class BaseAgent:
        def __init__(self):
            self.policy = policy

    base = BaseAgent()
    registry = SpecializedAgentRegistry()
    registry.register(DummySpecializedAgent("research"))

    orchestrator = Orchestrator(base, specialized_agent_registry=registry)

    # Request delegation to research by user 'charlie'
    resp = orchestrator.run({"delegations": [{"id": "d1", "agent": "research", "query": "do work"}]}, user_id="charlie")
    assert resp.success is False
    # Ensure the delegation result shows unauthorized for research
    assert isinstance(resp.output, list)
    assert resp.output[0].success is False
    assert "Unauthorized access to specialized agent" in (resp.output[0].error or "")
