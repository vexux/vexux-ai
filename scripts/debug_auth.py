import traceback
from core.policy.default import DefaultPolicy
from core.contracts.execution import Task, AgentContext
from agent.execution_manager import ExecutionManager
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph

class TestPolicy(DefaultPolicy):
    def __init__(self, deny_map=None):
        super().__init__()
        self.deny_map = deny_map or {}
    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        denied = self.deny_map.get(resource_type, set())
        if resource_name in denied:
            return DefaultPolicy.PolicyDecision(False, f"denied")
        return DefaultPolicy.PolicyDecision(True)

kr = KnowledgeGraphRegistry()
g1 = InMemoryKnowledgeGraph(); g1.name = 'customer_graph'; g1.add_node('n1', properties={})
g2 = InMemoryKnowledgeGraph(); g2.name = 'fraud_graph'; g2.add_node('n2', properties={})
kr.register(g1); kr.register(g2)
policy = TestPolicy(deny_map={'knowledge_graph': {'fraud_graph'}})
em = ExecutionManager(knowledge_graph_registry=kr, policy=policy)

task = Task(id='t1', description='multi', input={'query':'q', 'graph_requests':[{'graph_name':'customer_graph','operation':'get_node','params':{'node_id':'n1'}},{'graph_name':'fraud_graph','operation':'get_node','params':{'node_id':'n2'}}]}, metadata={'capability':'retrieval'})
ctx = AgentContext(request_id='r1', user_id='bob')

try:
    res = em.execute(task, ctx)
    print('RES:', res)
except Exception as e:
    print('EXC:', e)
    traceback.print_exc()
