from rag.loader import DocumentLoader
from rag.chunker import TextChunker
from rag.embedder import Embedder
from rag.vectorstore import VectorStore
from rag.retriever import Retriever
from rag.prompt_builder import PromptBuilder

from training.inference import InferencePipeline


class RAGPipeline:

    def __init__(
        self,
        top_k=3,
        relevance_threshold=None,
    ):

        self.top_k = top_k
        self.relevance_threshold = relevance_threshold

        self.loader = DocumentLoader(
            "data/documents"
        )

        self.chunker = TextChunker()

        self.embedder = Embedder()

        self.initialize()

    def initialize(self):

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

        self.inference = InferencePipeline()

    def retrieve(
        self,
        query,
        k=None,
    ):

        if k is None:
            k = self.top_k

        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("Retrieval top_k must be a positive integer.")

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