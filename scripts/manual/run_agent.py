import sqlite3
import tempfile
from pathlib import Path

from core.composition import create_agent
from core.knowledge.multi_graph import build_fraud_investigation_graphs
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.policy.default import DefaultPolicy, PolicyDecision


class DemoPolicy(DefaultPolicy):
    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if actor == "support_user" and resource_name == "fraud_graph":
            return PolicyDecision(False, "support_user cannot access fraud_graph", "demo_policy")
        return super().authorize_resource(actor, resource_type, resource_name, action, context)


def main():

    agent = create_agent()
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
            default_query="SELECT * FROM accounts",
            aliases=("business db", "sqlite", "sqlite db", "sqlite database"),
        )
        sql.name = "business_db"
        sources.register(sql)
        agent.resource_router.knowledge_graph_registry = graphs
        agent.resource_router.knowledge_source_registry = sources
        agent.execution_manager.knowledge_graph_registry = graphs
        agent.execution_manager.knowledge_source_registry = sources
        agent.knowledge_graph_registry = graphs
        policy = DemoPolicy()
        agent.policy = policy
        agent.execution_manager.policy = policy
        actor = "investigator"
        session_id = "terminal-session"

        print("=" * 60)
        print("Vexux AI Interactive Terminal")
        print("Type 'exit' or 'quit' to stop. Use '/actor investigator' or '/actor support_user'.")
        print("=" * 60)

        while True:
            query = input("\nYou: ").strip()

            if query.lower() in {"exit", "quit"}:
                print("Exiting...")
                break

            if query.lower().startswith("/actor "):
                actor = query.split(None, 1)[1].strip()
                print(f"Actor: {actor}")
                continue

            if not query:
                continue

            try:
                route = agent.resource_router.route(query)
                print("\nDetected resources:")
                for selection in route.selections if route else []:
                    print(f"- {selection.name}")
            except ValueError as exc:
                print(f"\nRouting error: {exc}")
            result = agent.run(query, session_id=session_id, user_id=actor)

            print("\nAgent:")
            print(result.output)

            if result.error:
                print("\nError:")
                print(result.error)

            sources_used = {
                item.source
                for observation in result.trace
                for evidence in (
                    [observation.output.get("evidence")]
                    if isinstance(observation.output, dict)
                    else []
                )
                if evidence is not None
                for item in getattr(evidence, "items", [])
            }
            if sources_used:
                print("Sources:", sorted(sources_used))
            print("\nSuccess:", result.success)
            print("Trace length:", len(result.trace))


if __name__ == "__main__":
    main()