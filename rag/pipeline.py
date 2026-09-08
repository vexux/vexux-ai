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
        relevance_threshold=None,
        enable_inference=True,
    ):

        self.top_k = top_k
        self.relevance_threshold = relevance_threshold
        self.enable_inference = enable_inference

        self.loader = DocumentLoader(
            "data/documents"
        )

        self.chunker = TextChunker()

        self.embedder = None
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
                document["content"]
            )

            chunks.extend(document_chunks)

        vectors = self.embedder.encode(chunks)

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

        return [
            result
            for result in results
            if result["score"] >= self.relevance_threshold
        ]

    def ask(self, question):
        self._ensure_initialized()
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

        retrieved = self.retrieve(
            question
        )

        prompt = PromptBuilder.build(
            question,
            retrieved
        )

        answer = self.inference.generate(
            prompt
        )

        return answer