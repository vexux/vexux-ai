"""Interactive runner for the synthetic reference composition."""

from scripts.manual.demo_fixtures import create_demo_agent


def main():
    with create_demo_agent() as agent:
        actor = "investigator"
        session_id = "terminal-session"

        print("=" * 60)
        print("Vexux AI Interactive Terminal")
        print("Type 'exit' or 'quit' to stop. Use '/actor investigator' or '/actor support_user'.")
        print("Resource-aware demo queries include:")
        print("  - Give me information about C1001 from the customer graph.")
        print("  - Give me data from the customer graph and fraud graph for C1001.")
        print("  - Am I allowed to access customer_graph and fraud_graph?")
        print("  - Am I allowed to access fraud_graph?")
        print("Note: entity IDs alone such as 'C1001' are not resources; mention the graph explicitly.")
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
