from typing import Protocol, Dict, Any, List, Optional


class KnowledgeGraphContract(Protocol):
    """Domain-agnostic knowledge graph contract (protocol).

    Implementations must remain generic and not include domain-specific entity logic.
    """

    @property
    def name(self) -> str:
        ...

    def add_node(self, node_id: str, label: Optional[str] = None, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ...

    def get_node(self, node_id: str) -> Dict[str, Any]:
        ...

    def remove_node(self, node_id: str) -> None:
        ...

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        rel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    def get_relationship(self, rel_id: str) -> Dict[str, Any]:
        ...

    def remove_relationship(self, rel_id: str) -> None:
        ...

    def get_neighbors(self, node_id: str, direction: str = "outgoing") -> List[Dict[str, Any]]:
        ...
