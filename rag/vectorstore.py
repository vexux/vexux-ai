import faiss
import numpy as np


class VectorStore:

    def __init__(self, dimension):

        self.index = faiss.IndexFlatIP(dimension)

        self.documents = []

    def add(self, vectors, documents):
        vectors = np.asarray(vectors).astype("float32")
        if vectors.ndim != 2:
            raise ValueError("Embedding vectors must be a two-dimensional array.")
        if vectors.shape[0] != len(documents):
            raise ValueError("Each embedding vector must have a corresponding document.")
        if not documents:
            return
        self.index.add(vectors)
        self.documents.extend(documents)

    def search(self, query_vector, k=3):
        query_vector = np.asarray(query_vector).astype("float32")
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("Search top_k must be a positive integer.")
        if self.index.ntotal == 0:
            return []
        scores, indices = self.index.search(query_vector, min(k, self.index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            stored_document = self.documents[idx]
            if isinstance(stored_document, dict):
                result = {
                    "score": float(np.clip(score, -1.0, 1.0)),
                    "document": stored_document["content"],
                }
                result.update(
                    {
                        key: value
                        for key, value in stored_document.items()
                        if key != "content"
                    }
                )
                results.append(result)
            else:
                results.append(
                    {
                        "score": float(np.clip(score, -1.0, 1.0)),
                        "document": stored_document,
                    }
                )
        return results