from typing import Any, Dict, List

from rag.pipeline import RAGPipeline
from core.contracts.evidence import Evidence, EvidenceSet


class RAGKnowledgeSource:

    def __init__(
        self,
        pipeline: RAGPipeline,
    ):

        self.pipeline = pipeline

    @property
    def name(self) -> str:

        return "rag"

    @property
    def description(self) -> str:

        return "Retrieves relevant document chunks using the local RAG pipeline."

    @property
    def capabilities(self) -> List[str]:

        return ["semantic_search", "document_retrieval"]

    def retrieve(
        self,
        query: str,
        k: int | None = None,
    ) -> List[Dict[str, Any]]:

        if k is None:
            return self.pipeline.retrieve(query)

        return self.pipeline.retrieve(query, k=k)

    def normalize(self, results):
        evidence = EvidenceSet()
        for result in results:
            metadata = {
                key: result[key]
                for key in (
                    "source",
                    "document_name",
                    "document_title",
                    "title",
                    "chunk_index",
                    "score",
                )
                if key in result
            }
            evidence.add(
                Evidence(
                    self.name,
                    str(result.get("document", "")),
                    "document",
                    metadata,
                )
            )
        return evidence
