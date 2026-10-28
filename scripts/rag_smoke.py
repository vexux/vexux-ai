"""Run a local BGE/FAISS retrieval smoke check over fraud reference guidance."""

from __future__ import annotations

import sys
from pathlib import Path

from rag.pipeline import RAGPipeline


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "apps" / "fraud" / "knowledge"


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = "What should an investigator consider when customers share a device?"
    pipeline = RAGPipeline(
        enable_inference=False,
        documents_path=KNOWLEDGE_DIR,
    )
    results = pipeline.retrieve(query)
    if not results:
        print("No sufficiently relevant knowledge context was found.")
        return 1
    for result in results:
        print(
            f"[{result['source']} — {result['title']} "
            f"(chunk {result['chunk_index']}, score {result['score']:.3f})]"
        )
        print(result["document"])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
