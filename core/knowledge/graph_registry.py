from typing import Any, Dict, List, Optional

from core.contracts.knowledge_graph import KnowledgeGraphContract


class KnowledgeGraphRegistry:

    def __init__(self):
        self._graphs: Dict[str, KnowledgeGraphContract] = {}
        self._default_name: Optional[str] = None

    def register(self, graph: KnowledgeGraphContract) -> None:
        if graph.name in self._graphs:
            raise ValueError(f"Knowledge graph already registered: {graph.name}")
        self._graphs[graph.name] = graph
        if self._default_name is None:
            self._default_name = graph.name

    def get(self, name: Optional[str] = None) -> KnowledgeGraphContract:
        if name is None:
            name = self._default_name
        if name is None:
            raise KeyError("No knowledge graph registered")
        if name not in self._graphs:
            raise KeyError(f"Knowledge graph not found: {name}")
        return self._graphs[name]

    def describe_graphs(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": g.name,
            }
            for g in self._graphs.values()
        ]
