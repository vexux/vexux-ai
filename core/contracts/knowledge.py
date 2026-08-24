from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class KnowledgeRequest:
    """Domain-agnostic contract representing a knowledge decision/request.

    Fields:
    - kind: one of "rag", "knowledge_source", or "graph" indicating which
      subsystem should be used to satisfy the request.
    - query: the text query or user expression to be satisfied by the chosen
      knowledge capability.
    - source: optional stable source name when selecting a registered source or
      graph name. For RAG this will be "rag".
    - operation: optional operation hint (e.g., "search", "lookup") kept
      generic and domain-agnostic.
    - params: optional structured parameters forwarded to the executing
      capability (kept generic).
    """

    kind: str
    query: str
    source: Optional[str] = None
    operation: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
