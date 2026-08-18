from rag.loader import DocumentLoader
from rag.chunker import TextChunker
from rag.embedder import Embedder
from rag.vectorstore import VectorStore
from rag.retriever import Retriever
from rag.prompt_builder import PromptBuilder

from training.inference import InferencePipeline


class RAGPipeline:

    def __init__(self):

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

    def ask(self, question):

        retrieved = self.retriever.retrieve(
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