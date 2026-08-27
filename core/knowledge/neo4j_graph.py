"""Neo4j adapter for the domain-neutral knowledge graph contract."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.contracts.knowledge_graph import KnowledgeGraphContract


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Neo4jKnowledgeGraph:
    """Map the generic graph contract to parameterized Neo4j queries."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        name: str = "neo4j",
        database: Optional[str] = None,
        driver: Any = None,
    ):
        if not uri or not username or not password:
            raise ValueError(
                "Neo4j configuration requires NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD."
            )
        if not name:
            raise ValueError("Neo4j graph name must not be empty.")
        self._name = name
        self.database = database
        if driver is not None:
            self._driver = driver
        else:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError(
                    "Neo4j support requires the optional 'neo4j' package."
                ) from exc
            self._driver = GraphDatabase.driver(uri, auth=(username, password))

    @property
    def name(self) -> str:
        return self._name

    def _session(self):
        kwargs = {"database": self.database} if self.database else {}
        return self._driver.session(**kwargs)

    @staticmethod
    def _record_value(record: Any, key: str) -> Any:
        if isinstance(record, dict):
            return record.get(key)
        if hasattr(record, "get"):
            return record.get(key)
        return None

    @classmethod
    def _node(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            raise KeyError("Node not found")
        properties = dict(getattr(value, "_properties", {}) or {})
        if isinstance(value, dict):
            properties = dict(value.get("properties", value))
        node_id = properties.get("id", getattr(value, "element_id", None))
        labels = list(getattr(value, "labels", []) or [])
        return {
            "id": str(node_id) if node_id is not None else "",
            "label": labels[0] if labels else None,
            "properties": properties,
        }

    @classmethod
    def _relationship(cls, value: Any, source: Any = None, target: Any = None) -> Dict[str, Any]:
        if value is None:
            raise KeyError("Relationship not found")
        properties = dict(getattr(value, "_properties", {}) or {})
        if isinstance(value, dict):
            properties = dict(value.get("properties", value))
        rel_id = properties.get("id", getattr(value, "element_id", None))
        rel_type = getattr(value, "type", None)
        if isinstance(value, dict):
            rel_type = value.get("type", rel_type)
        result = {
            "id": str(rel_id) if rel_id is not None else "",
            "source": cls._node(source)["id"] if source is not None else "",
            "target": cls._node(target)["id"] if target is not None else "",
            "type": rel_type,
            "properties": properties,
        }
        return result

    @staticmethod
    def _label(label: Optional[str]) -> str:
        if label is None:
            return ""
        if not _IDENTIFIER.fullmatch(label):
            raise ValueError("Neo4j node labels must be valid identifiers.")
        return f":{label}"

    def _run_one(self, query: str, **parameters: Any) -> Any:
        try:
            with self._session() as session:
                result = session.run(query, **parameters)
                return result.single()
        except (KeyError, ValueError):
            raise
        except Exception as exc:
            raise RuntimeError("Neo4j query failed.") from exc

    def add_node(self, node_id: str, label: Optional[str] = None, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        record = self._run_one(
            f"CREATE (n{self._label(label)}) SET n.id = $node_id, n += $properties RETURN n",
            node_id=node_id,
            properties=dict(properties or {}),
        )
        return self._node(self._record_value(record, "n"))

    def get_node(self, node_id: str) -> Dict[str, Any]:
        record = self._run_one(
            "MATCH (n {id: $node_id}) RETURN n",
            node_id=node_id,
        )
        if record is None:
            raise KeyError(f"Node not found: {node_id}")
        return self._node(self._record_value(record, "n"))

    def remove_node(self, node_id: str) -> None:
        record = self._run_one(
            "MATCH (n {id: $node_id}) RETURN n",
            node_id=node_id,
        )
        if record is None:
            raise KeyError(f"Node not found: {node_id}")
        try:
            with self._session() as session:
                session.run("MATCH (n {id: $node_id}) DETACH DELETE n", node_id=node_id)
        except Exception as exc:
            raise RuntimeError("Neo4j query failed.") from exc

    def add_relationship(self, source_id: str, target_id: str, rel_type: Optional[str] = None, properties: Optional[Dict[str, Any]] = None, rel_id: Optional[str] = None) -> Dict[str, Any]:
        relationship_type = rel_type or "RELATED_TO"
        if not _IDENTIFIER.fullmatch(relationship_type):
            raise ValueError("Neo4j relationship types must be valid identifiers.")
        relationship_id = rel_id or f"{source_id}->{target_id}:{relationship_type}"
        record = self._run_one(
            f"MATCH (source {{id: $source_id}}), (target {{id: $target_id}}) "
            f"CREATE (source)-[r:{relationship_type}]->(target) "
            "SET r.id = $rel_id, r += $properties RETURN source, target, r",
            source_id=source_id,
            target_id=target_id,
            rel_id=relationship_id,
            properties=dict(properties or {}),
        )
        if record is None:
            raise KeyError("Source or target node not found")
        return self._relationship(
            self._record_value(record, "r"),
            self._record_value(record, "source"),
            self._record_value(record, "target"),
        )

    def get_relationship(self, rel_id: str) -> Dict[str, Any]:
        record = self._run_one(
            "MATCH (source)-[r {id: $rel_id}]-(target) RETURN source, target, r",
            rel_id=rel_id,
        )
        if record is None:
            raise KeyError(f"Relationship not found: {rel_id}")
        return self._relationship(
            self._record_value(record, "r"),
            self._record_value(record, "source"),
            self._record_value(record, "target"),
        )

    def remove_relationship(self, rel_id: str) -> None:
        record = self._run_one(
            "MATCH ()-[r {id: $rel_id}]-() RETURN r",
            rel_id=rel_id,
        )
        if record is None:
            raise KeyError(f"Relationship not found: {rel_id}")
        try:
            with self._session() as session:
                session.run("MATCH ()-[r {id: $rel_id}]-() DELETE r", rel_id=rel_id)
        except Exception as exc:
            raise RuntimeError("Neo4j query failed.") from exc

    def get_neighbors(self, node_id: str, direction: str = "outgoing") -> List[Dict[str, Any]]:
        patterns = {
            "outgoing": "(source {id: $node_id})-[r]->(node)",
            "incoming": "(source)-[r]->(node {id: $node_id})",
            "both": "(source {id: $node_id})-[r]-(node)",
        }
        if direction not in patterns:
            raise ValueError("Direction must be outgoing, incoming, or both.")
        record_query = f"MATCH {patterns[direction]} RETURN source, node, r"
        try:
            with self._session() as session:
                records = session.run(record_query, node_id=node_id)
                rows = list(records)
        except Exception as exc:
            raise RuntimeError("Neo4j query failed.") from exc
        if not rows:
            self.get_node(node_id)
        results = []
        for record in rows:
            source = self._record_value(record, "source")
            node = self._record_value(record, "node")
            relationship = self._relationship(self._record_value(record, "r"), source, node)
            actual_direction = "incoming" if direction == "incoming" else "outgoing"
            results.append({
                "relationship": relationship,
                "node": self._node(node),
                "direction": actual_direction,
            })
        return results

