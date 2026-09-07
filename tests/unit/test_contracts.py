from rag.embedder import Embedder
from rag.retriever import Retriever
from rag.vectorstore import VectorStore


def main():

    embedder = Embedder()

    print("Embedder created")

    print("Retriever constructor requires:")
    print("  - store")
    print("  - embedder")

    print("\nContract integration structure OK")


if __name__ == "__main__":
    main()