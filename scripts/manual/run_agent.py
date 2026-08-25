from core.composition import create_agent


def main():

    agent = create_agent()
    session_id = "terminal-session"

    print("=" * 60)
    print("Vexux AI Interactive Terminal")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 60)

    while True:

        query = input("\nYou: ").strip()

        if query.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if not query:
            continue

        result = agent.run(
            query,
            session_id=session_id
        )

        print("\nAgent:")
        print(result.output)

        if result.error:
            print("\nError:")
            print(result.error)

        print("\nSuccess:", result.success)
        print("Trace length:", len(result.trace))


if __name__ == "__main__":
    main()