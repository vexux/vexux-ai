import pytest

from core.audit_logger import clear_events, get_events
from core.contracts.audit import AuditEvent
from apps.fraud.composition import create_fraud_investigation_fixture, create_fraud_investigation_request
from core.policy.default import DefaultPolicy
from agent.execution_manager import ExecutionManager
from core.contracts.execution import Task, AgentContext


class AllowAllPolicy(DefaultPolicy):
    pass


def test_multi_graph_audit_events_present():
    clear_events()
    registry = create_fraud_investigation_fixture()
    policy = AllowAllPolicy()
    em = ExecutionManager(knowledge_graph_registry=registry, policy=policy)

    mg_request = create_fraud_investigation_request(query="Investigate C1001", customer_id="C1001", device_id="D500")
    task = Task(id="t-audit-1", description="audit test", input={"query": mg_request.query, "graph_requests": mg_request.as_dict_list(), "customer_id": "C1001"}, metadata={"capability": "retrieval"})
    ctx = AgentContext(request_id="r1", user_id="investigator")

    res = em.execute(task, ctx)
    events = get_events()
    # At least one request_started and two task_started/task_completed should be present
    types = [e.event_type for e in events]
    assert "request_started" in types
    # ensure both graph names appear in at least one event
    resources = [e.resource_name for e in events if e.resource_name]
    assert "customer_graph" in resources
    assert "fraud_graph" in resources
    authorization_events = [
        event for event in events
        if event.event_type == "authorization_allowed"
    ]
    assert authorization_events
    assert all(event.metadata.get("actor_id") == "investigator" for event in authorization_events)
    assert all(event.request_id == "r1" for event in authorization_events)
    # request should complete
    assert any(e.event_type == "request_completed" and e.status == "completed" for e in events)
    assert res.success
