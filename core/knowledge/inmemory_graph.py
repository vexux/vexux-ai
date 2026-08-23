from typing import Dict, Any, Optional, List


class InMemoryKnowledgeGraph:
    """Deterministic in-memory knowledge graph backend.

    - Nodes are stored in an insertion-ordered dict.
    - Relationships are stored with generated incremental IDs.
    - Duplicate nodes or relationships raise ValueError.
    - Missing nodes/relationships raise KeyError.
    - Removing a node that has relationships raises ValueError (must remove relationships first).
    """

    name = "inmemory"

    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._relationships: Dict[str, Dict[str, Any]] = {}
        # adjacency
        self._outgoing: Dict[str, List[str]] = {}
        self._incoming: Dict[str, List[str]] = {}
        self._rel_counter = 0

    def add_node(self, node_id: str, label: Optional[str] = None, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if node_id in self._nodes:
            raise ValueError(f"Node already exists: {node_id}")
        node = {
            "id": node_id,
            "label": label,
            "properties": dict(properties) if properties else {},
        }
        self._nodes[node_id] = node
        self._outgoing.setdefault(node_id, [])
        self._incoming.setdefault(node_id, [])
        return node

    def get_node(self, node_id: str) -> Dict[str, Any]:
        if node_id not in self._nodes:
            raise KeyError(f"Node not found: {node_id}")
        return self._nodes[node_id]

    def remove_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            raise KeyError(f"Node not found: {node_id}")
        if self._outgoing.get(node_id) or self._incoming.get(node_id):
            # If there are any relationships still present, do not silently remove them.
            raise ValueError(f"Node has relationships; remove relationships first: {node_id}")
        # safe to remove
        self._nodes.pop(node_id)
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)

    def _generate_rel_id(self) -> str:
        self._rel_counter += 1
        return f"rel:{self._rel_counter}"

    def add_relationship(self, source_id: str, target_id: str, rel_type: Optional[str] = None, properties: Optional[Dict[str, Any]] = None, rel_id: Optional[str] = None) -> Dict[str, Any]:
        if source_id not in self._nodes:
            raise KeyError(f"Source node not found: {source_id}")
        if target_id not in self._nodes:
            raise KeyError(f"Target node not found: {target_id}")
        # check duplicates (same source, target, type, properties)
        props = dict(properties) if properties else {}
        for existing in self._relationships.values():
            if existing["source"] == source_id and existing["target"] == target_id and existing.get("type") == rel_type and existing.get("properties") == props:
                raise ValueError("Duplicate relationship")
        if rel_id is None:
            rel_id = self._generate_rel_id()
        elif rel_id in self._relationships:
            raise ValueError(f"Relationship id already exists: {rel_id}")
        rel = {
            "id": rel_id,
            "source": source_id,
            "target": target_id,
            "type": rel_type,
            "properties": props,
        }
        self._relationships[rel_id] = rel
        self._outgoing.setdefault(source_id, []).append(rel_id)
        self._incoming.setdefault(target_id, []).append(rel_id)
        return rel

    def get_relationship(self, rel_id: str) -> Dict[str, Any]:
        if rel_id not in self._relationships:
            raise KeyError(f"Relationship not found: {rel_id}")
        return self._relationships[rel_id]

    def remove_relationship(self, rel_id: str) -> None:
        if rel_id not in self._relationships:
            raise KeyError(f"Relationship not found: {rel_id}")
        rel = self._relationships.pop(rel_id)
        source = rel["source"]
        target = rel["target"]
        if source in self._outgoing:
            try:
                self._outgoing[source].remove(rel_id)
            except ValueError:
                pass
        if target in self._incoming:
            try:
                self._incoming[target].remove(rel_id)
            except ValueError:
                pass

    def get_neighbors(self, node_id: str, direction: str = "outgoing") -> List[Dict[str, Any]]:
        if node_id not in self._nodes:
            raise KeyError(f"Node not found: {node_id}")
        neighbors = []
        if direction in ("outgoing", "both"):
            for rel_id in self._outgoing.get(node_id, []):
                rel = self._relationships[rel_id]
                neighbor = self._nodes[rel["target"]]
                neighbors.append({"relationship": rel, "node": neighbor, "direction": "outgoing"})
        if direction in ("incoming", "both"):
            for rel_id in self._incoming.get(node_id, []):
                rel = self._relationships[rel_id]
                neighbor = self._nodes[rel["source"]]
                neighbors.append({"relationship": rel, "node": neighbor, "direction": "incoming"})
        return neighbors
