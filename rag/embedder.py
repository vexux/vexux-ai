class Embedder:
    def __init__(self, model_name="BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self.model = None

    def _ensure_model(self):
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
            except Exception as exc:
                raise RuntimeError(
                    f"RAG embedding model initialization failed: {exc}"
                ) from exc
        return self.model

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]

        vectors = self._ensure_model().encode(
            texts,
            normalize_embeddings=True
        )

        return vectors