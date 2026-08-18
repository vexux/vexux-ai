from typing import List, Dict, Any

from rag.embedder import Embedder
from rag.vectorstore import VectorStore


class Retriever:

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
    ):

        self.store = store
        self.embedder = embedder

    def retrieve(
        self,
        query: str,
        k: int = 3,
    ) -> List[Dict[str, Any]]:

        query_vector = self.embedder.encode(query)

        results = self.store.search(
            query_vector,
            k=k,
        )

        return results