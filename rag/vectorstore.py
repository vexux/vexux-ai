import faiss
import numpy as np


class VectorStore:

    def __init__(self, dimension):

        self.index = faiss.IndexFlatIP(dimension)

        self.documents = []

    def add(self, vectors, documents):

        vectors = np.asarray(vectors).astype("float32")

        self.index.add(vectors)

        self.documents.extend(documents)

    def search(self, query_vector, k=3):

        query_vector = np.asarray(query_vector).astype("float32")

        scores, indices = self.index.search(
            query_vector,
            k
        )

        results = []

        for score, idx in zip(scores[0], indices[0]):

            results.append({

                "score": float(score),

                "document": self.documents[idx]

            })

        return results