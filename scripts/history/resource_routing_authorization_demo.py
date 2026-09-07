"""Interactive deterministic resource-routing and authorization demonstration."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task
from apps.fraud.composition import build_fraud_investigation_graphs
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.resource_router import ResourceRouter
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.policy.default import DefaultPolicy


class DemoPolicy(DefaultPolicy):
    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if actor == "support_user" and resource_name == "fraud_graph":
            from core.policy.default import PolicyDecision
            return PolicyDecision(False, "support_user cannot access fraud_graph", "demo_policy")
        return super().authorize_resource(actor, resource_type, resource_name, action, context)


def run_once(actor: str, query: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "business.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                "CREATE TABLE accounts (account_id TEXT, customer_id TEXT, status TEXT);"
                "INSERT INTO accounts VALUES ('A100', 'C1001', 'active');"
            )
        finally:
            connection.close()

        graphs = build_fraud_investigation_graphs()
        sources = KnowledgeSourceRegistry()
        sql = SQLKnowledgeSource(
            SQLiteBackend(str(database)),
            default_query="SELECT * FROM accounts WHERE customer_id = ?",
            aliases=("business db", "sqlite db", "sqlite"),
        )
        sql.name = "business_db"
        sources.register(sql)
        router = ResourceRouter(sources, graphs)
        route = router.route(query)
        print(f"\nactor = {actor}")
        print(f"detected resources = {[item.name for item in route.selections] if route else []}")
        if route is None:
            print("routing = default behavior (no explicit resources)")
            return

        policy = DemoPolicy()
        denied = [
            item.name
            for item in route.selections
            if not policy.authorize_resource(actor, item.resource_type, item.name, "read").allowed
        ]
        if denied:
            print(f"authorization = denied: {denied}")
            print("execution = skipped for denied resources")
            print("final result = controlled authorization failure")
            return

        manager = ExecutionManager(
            knowledge_graph_registry=graphs,
            knowledge_source_registry=sources,
            policy=policy,
        )
        results = []
        if route.graph_requests:
            results.append(manager.execute(
                Task(
                    id="routed-graphs",
                    description="Retrieve requested graphs",
                    input={"query": query, "graph_requests": route.graph_requests},
                    metadata={"capability": "retrieval"},
                ),
                AgentContext(request_id="routing-demo", user_id=actor),
            ))
        for index, source in enumerate(route.source_tasks, start=1):
            results.append(manager.execute(
                Task(
                    id=f"routed-source-{index}",
                    description=f"Retrieve {source['source']}",
                    input=source,
                    metadata={"capability": "retrieval"},
                ),
                AgentContext(request_id="routing-demo", user_id=actor),
            ))
        print("authorization = allowed")
        print(f"execution = {[result.success for result in results]}")
        print("final result = successful multi-source retrieval")


def main() -> None:
    query = "hi can you tell me data from the customer graph, fraud graph and sqlite db for C1001"
    actor = "investigator"
    print("Commands: /actor investigator, /actor support_user, /run, /quit")
    while True:
        try:
            command = input(f"[{actor}]> ").strip()
        except EOFError:
            break
        if command == "/quit":
            break
        if command.startswith("/actor "):
            actor = command.split(None, 1)[1].strip()
            print(f"current actor = {actor}")
        elif command == "/run":
            run_once(actor, query)
        elif command:
            print("Use /actor investigator, /actor support_user, /run, or /quit.")


if __name__ == "__main__":
    main()
