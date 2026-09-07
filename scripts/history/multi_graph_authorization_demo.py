"""Manual demo: multi-graph end-to-end authorization demo (Phase 25 synthetic scenario).

Run from the repository root:
    python scripts/manual/multi_graph_authorization_demo.py

This demo is deterministic and uses the in-memory graphs already present in
core.knowledge.multi_graph. It exercises the resource-aware authorization
boundary by running two scenarios:

- Scenario A: actor 'investigator' authorized for both graphs -> both graphs execute,
  aggregation happens, facts shown.
- Scenario B: actor 'support_user' denied access to 'fraud_graph' -> controlled
  failure before any graph executes (per Phase 24 deterministic policy).

The demo does not change production behavior; it only instantiates a custom
policy instance for demonstration and prints observable metadata.
"""

from apps.fraud.composition import (
    create_fraud_investigation_fixture,
    create_fraud_investigation_request,
)
from core.policy.default import DefaultPolicy, PolicyDecision
from agent.execution_manager import ExecutionManager
from core.contracts.execution import Task, AgentContext


class DemoPolicy(DefaultPolicy):
    """Simple actor-aware demo policy that supports per-actor deny lists.

    Configuration is provided via actor_deny_map which maps actor -> set of
    (resource_type, resource_name) tuples that are denied. The policy prints
    authorization checks so the demo can show the decisions.
    """

    def __init__(self, actor_deny_map=None):
        super().__init__()
        self.actor_deny_map = actor_deny_map or {}

    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        denied = False
        if actor in self.actor_deny_map:
            denies_for_actor = self.actor_deny_map.get(actor) or set()
            if (resource_type, resource_name) in denies_for_actor:
                denied = True
        decision = PolicyDecision(False, "denied", "demo_policy") if denied else PolicyDecision(True, None, "demo_policy")
        # Print a concise authorization observation (safe to display in demo)
        print(f"AUTH CHECK: actor={actor!r} resource_type={resource_type!r} resource_name={resource_name!r} action={action!r} -> allowed={decision.allowed}")
        return decision


def run_scenario(actor: str, policy: DemoPolicy):
    print("\n" + "=" * 60)
    print(f"Running scenario for actor: {actor}")

    # Build graphs and registry
    registry = create_fraud_investigation_fixture()

    # Build a deterministic multi-graph request using helper
    mg_request = create_fraud_investigation_request(
        query=f"Investigate customer C1001 and identify accounts, fraud cases, and devices.",
        customer_id="C1001",
        device_id="D500",
    )

    # Print requested graphs for visibility
    requested_graphs = [r.graph_name for r in mg_request.requests]
    print(f"Requested graphs: {requested_graphs}")

    # Create an ExecutionManager wired with the registry and policy
    em = ExecutionManager(knowledge_graph_registry=registry, policy=policy)

    # Build a Task representing a retrieval with multi-graph requests
    task = Task(
        id="demo-multi-1",
        description="Multi-graph fraud investigation demo",
        input={
            "query": mg_request.query,
            "graph_requests": mg_request.as_dict_list(),
            "customer_id": "C1001",
        },
        metadata={"capability": "retrieval"},
    )

    ctx = AgentContext(request_id="demo-req-1", user_id=actor)

    # Execute and capture result
    print("Executing multi-graph request (authorization enforced prior to execution)...")
    res = em.execute(task, ctx)

    # Show what happened
    print(f"Execution success: {res.success}")
    print(f"Execution error: {res.error}")
    # metadata may contain capability/source
    print(f"Execution metadata: {res.metadata}")

    if res.success and isinstance(res.output, dict):
        summary = res.output.get("summary") or {}
        facts = res.output.get("facts") or []
        print("Aggregated summary:")
        print(summary)
        print("Facts:")
        for f in facts:
            print(" -", f)
        # Show evidence provenance counts if present
        evidence = res.output.get("evidence")
        if evidence is not None:
            try:
                # EvidenceSet stringification may be large; just show a count
                print(f"Evidence items: {len(list(evidence))}")
            except Exception:
                print("Evidence: <uninspectable>")
    else:
        print("No aggregation output (controlled failure or empty results).")


def main():
    # Configure demo policy: 'support_user' is denied access to fraud_graph
    actor_deny_map = {
        "support_user": {("knowledge_graph", "fraud_graph")},
    }
    policy = DemoPolicy(actor_deny_map=actor_deny_map)

    # Scenario A: investigator (allowed)
    run_scenario("investigator", policy)

    # Scenario B: support_user (denied fraud_graph)
    run_scenario("support_user", policy)


if __name__ == "__main__":
    main()
