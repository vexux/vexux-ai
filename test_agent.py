from core.composition import create_agent


def main():

    agent = create_agent()

    queries = [
    
        "What is EC2 and calculate abc",
    ]

    for query in queries:

        print("=" * 60)

        print("User:")
        print(query)

        result = agent.run(
            query
        )

        print("\nResult:")

        print(
            "Success:",
            result.success
        )

        print(
            "Output:",
            result.output
        )

        print(
            "Error:",
            result.error
        )


if __name__ == "__main__":
    main()