from rag.pipeline import RAGPipeline


def main():

    rag = RAGPipeline()

    question = "What is EC2?"

    answer = rag.ask(question)

    print("=" * 60)
    print("Question:")
    print(question)

    print("\nAnswer:")
    print(answer)

    print("=" * 60)


if __name__ == "__main__":
    main()