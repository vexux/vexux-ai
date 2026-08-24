from typing import Optional, Dict, Any

from core.contracts.knowledge import KnowledgeRequest


class KnowledgeDecision:
    """Decides which knowledge capability should handle a request.

    Responsibilities:
    - Normalize an incoming request into a KnowledgeRequest (domain-agnostic).
    - Validate that an explicitly requested source exists and is available.
    - Expose the available capabilities through the provided registries
      without executing any retrieval logic.

    NOTE: This component MUST NOT execute retrievals. It only expresses the
    decision and validates availability.
    """

    def __init__(
        self,
        rag: Optional[object] = None,
        knowledge_source_registry: Optional[object] = None,
        knowledge_graph_registry: Optional[object] = None,
    ) -> None:
        # rag: any object representing the RAG subsystem (presence means available)
        self.rag = rag
        self.knowledge_source_registry = knowledge_source_registry
        self.knowledge_graph_registry = knowledge_graph_registry

    def create_request(
        self,
        query: str,
        explicit_source: Optional[str] = None,
        operation: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeRequest:
        params = params or {}

        # If a specific source was explicitly requested, validate it and
        # return a KnowledgeRequest targeted to that capability.
        if explicit_source:
            name = explicit_source.strip()
            lname = name.lower()

            # Explicit RAG selection
            if lname == "rag":
                if self.rag is None:
                    raise ValueError("Requested source 'rag' is unavailable")
                return KnowledgeRequest(kind="rag", query=query, source="rag", operation=operation, params=params)

            # Explicit knowledge source (SQL / API docs / other registered sources)
            if self.knowledge_source_registry is not None:
                try:
                    source = self.knowledge_source_registry.get(name)
                    # We don't inspect capabilities deeply here; caller may use
                    # the source name to route. Return normalized request.
                    return KnowledgeRequest(kind="knowledge_source", query=query, source=source.name, operation=operation, params=params)
                except KeyError:
                    # fall through to graph check / final error
                    pass

            # Explicit graph selection
            if self.knowledge_graph_registry is not None:
                try:
                    graph = self.knowledge_graph_registry.get(name)
                    return KnowledgeRequest(kind="graph", query=query, source=graph.name, operation=operation, params=params)
                except KeyError:
                    pass

            # If nothing matched, it's a controlled unknown-source error — do not
            # silently fallback to another capability.
            raise KeyError(f"Unknown or unavailable knowledge source: {name}")

        # No explicit source: use discovery/default behavior in a deterministic order
        # 1) If a KnowledgeSourceRegistry has a default, prefer it (preserves existing behavior)
        if self.knowledge_source_registry is not None:
            try:
                default = self.knowledge_source_registry.get()
                return KnowledgeRequest(kind="knowledge_source", query=query, source=default.name, operation=operation, params=params)
            except KeyError:
                # no registered sources available — continue discovery
                pass

        # 2) If RAG is available, use it as a fallback default
        if self.rag is not None:
            return KnowledgeRequest(kind="rag", query=query, source="rag", operation=operation, params=params)

        # 3) If a knowledge graph registry has a default graph, use it
        if self.knowledge_graph_registry is not None:
            try:
                default_graph = self.knowledge_graph_registry.get()
                return KnowledgeRequest(kind="graph", query=query, source=default_graph.name, operation=operation, params=params)
            except KeyError:
                pass

        # No capabilities available
        raise RuntimeError("No knowledge capabilities are available to satisfy the request")
