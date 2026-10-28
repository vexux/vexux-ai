from pathlib import Path
import math

from rag.loader import DocumentLoader
from rag.chunker import TextChunker
from rag.embedder import Embedder
from rag.vectorstore import VectorStore
from rag.retriever import Retriever
from rag.prompt_builder import PromptBuilder


class RAGPipeline:

    def __init__(
        self,
        top_k=3,
        relevance_threshold=0.5,
        enable_inference=True,
        documents_path=None,
        embedder=None,
    ):
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("RAG top_k must be a positive integer.")
        if relevance_threshold is not None and (
            not isinstance(relevance_threshold, (int, float))
            or isinstance(relevance_threshold, bool)
            or not math.isfinite(relevance_threshold)
            or not -1.0 <= relevance_threshold <= 1.0
        ):
            raise ValueError("RAG relevance_threshold must be between -1 and 1 or None.")
        self.top_k = top_k
        self.relevance_threshold = relevance_threshold
        self.enable_inference = enable_inference

        default_documents = Path(__file__).resolve().parents[1] / "data" / "documents"
        self.loader = DocumentLoader(documents_path or default_documents)

        self.chunker = TextChunker()

        self.embedder = embedder
        self.store = None
        self.retriever = None
        self.inference = None
        self._initialized = False

    def _ensure_initialized(self):
        if getattr(self, "_initialized", False):
            return
        if getattr(self, "retriever", None) is not None:
            self._initialized = True
            return

        try:
            if self.embedder is None:
                self.embedder = Embedder()
            self.initialize()
        except Exception as exc:
            self.embedder = None
            self.store = None
            self.retriever = None
            raise RuntimeError(f"RAG retrieval initialization failed: {exc}") from exc

        self._initialized = True

    def initialize(self):
        if self.embedder is None:
            self.embedder = Embedder()

        documents = self.loader.load()

        chunks = []
        for document in documents:
            document_chunks = self.chunker.chunk(
                document["content"],
                metadata=document,
            )
            chunks.extend(document_chunks)
        if not chunks:
            raise ValueError("RAG documents did not produce any text chunks.")

        vectors = self.embedder.encode([chunk["content"] for chunk in chunks])
        if getattr(vectors, "ndim", None) != 2 or vectors.shape[0] != len(chunks):
            raise ValueError("RAG embedder must return one vector per text chunk.")

        self.store = VectorStore(
            vectors.shape[1]
        )

        self.store.add(
            vectors,
            chunks
        )

        self.retriever = Retriever(
            store=self.store,
            embedder=self.embedder,
        )

    def retrieve(
        self,
        query,
        k=None,
    ):

        if k is None:
            k = self.top_k

        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("Retrieval top_k must be a positive integer.")

        self._ensure_initialized()
        results = self.retriever.retrieve(
            query,
            k=k,
        )

        if self.relevance_threshold is None:
            return results
        if not isinstance(self.relevance_threshold, (int, float)):
            raise ValueError("Retrieval relevance_threshold must be numeric or None.")

        return [
            result
            for result in results
            if "score" not in result or result["score"] >= self.relevance_threshold
        ]

    def ask(self, question):
        retrieved = self.retrieve(
            question
        )
        if not retrieved:
            return "No sufficiently relevant knowledge context was found to answer that question."
        if self.inference is None and self.enable_inference:
            try:
                from training.inference import InferencePipeline
                self.inference = InferencePipeline()
            except Exception as exc:
                raise RuntimeError(
                    f"RAG local inference initialization failed: {exc}"
                ) from exc
        if self.inference is None:
            raise RuntimeError("RAG generation is disabled for this pipeline.")

        prompt = PromptBuilder.build(
            question,
            retrieved
        )

        answer = self.inference.generate(
            prompt
        )

        return answer