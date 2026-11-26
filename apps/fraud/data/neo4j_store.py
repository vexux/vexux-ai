"""Canonical fraud data initialization for a local Neo4j database."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


_DATASET_MARKER = "vexux_fraud"
_NODE_LABELS = frozenset({
    "Customer",
    "Account",
    "Device",
    "Address",
    "Merchant",
    "Transaction",
    "FraudCase",
    "FraudAlert",
})
_RELATIONSHIP_TYPES = frozenset({
    "OWNS",
    "HAS_TRANSACTION",
    "INVOLVES",
    "USES",
    "LIVES_AT",
    "INVOLVED_IN",
    "HAS_ALERT",
    "GENERATED_BY",
    "SHARES_DEVICE_WITH",
})


class Neo4jFraudStore:
    """Create constraints and seed only nodes tagged as Vexux fraud data."""

    def __init__(self, driver: Any, database: str | None = None):
        if driver is None:
            raise ValueError("A Neo4j driver is required.")
        self.driver = driver
        self.database = database

    def _session(self):
        options = {"database": self.database} if self.database else {}
        return self.driver.session(**options)

    def verify_connection(self) -> None:
        self.driver.verify_connectivity()

    def require_seeded(self) -> None:
        with self._session() as session:
            record = session.run(
                "MATCH (n:Customer {id: $customer_id}) "
                "WHERE n.vexux_dataset = $dataset RETURN count(n) AS count",
                customer_id="C1001",
                dataset=_DATASET_MARKER,
            ).single()
        if record is None or int(record["count"]) == 0:
            raise RuntimeError(
                "The canonical Neo4j fraud dataset is not present. "
                "Run 'python -m apps.fraud.data.cli seed' before starting real mode."
            )

    def initialize_schema(self) -> None:
        with self._session() as session:
            for label in sorted(_NODE_LABELS):
                constraint_name = f"vexux_fraud_{label.lower()}_id"
                session.run(
                    f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                ).consume()

    def seed(self, dataset: dict[str, Any]) -> None:
        self.initialize_schema()
        nodes_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in dataset["graph_nodes"]:
            label = node["label"]
            if label not in _NODE_LABELS:
                raise ValueError(f"Unsupported fraud graph node label: {label}")
            properties = dict(node["properties"])
            properties["vexux_dataset"] = _DATASET_MARKER
            nodes_by_label[label].append({
                "id": node["id"],
                "properties": properties,
            })

        relationships_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relationship in dataset["graph_relationships"]:
            rel_type = relationship["type"]
            if rel_type not in _RELATIONSHIP_TYPES:
                raise ValueError(f"Unsupported fraud graph relationship type: {rel_type}")
            properties = dict(relationship.get("properties") or {})
            properties["vexux_dataset"] = _DATASET_MARKER
            relationships_by_type[rel_type].append({
                "id": relationship["id"],
                "source": relationship["source"],
                "target": relationship["target"],
                "properties": properties,
            })

        def write_seed(transaction) -> None:
            for label, rows in sorted(nodes_by_label.items()):
                transaction.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label} {{id: row.id}}) "
                    "SET n += row.properties",
                    rows=rows,
                ).consume()
            for rel_type, rows in sorted(relationships_by_type.items()):
                record = transaction.run(
                    "UNWIND $rows AS row "
                    "MATCH (source {id: row.source}), (target {id: row.target}) "
                    f"MERGE (source)-[r:{rel_type} {{id: row.id}}]->(target) "
                    "SET r += row.properties RETURN count(r) AS count",
                    rows=rows,
                ).single()
                if record is None or int(record["count"]) != len(rows):
                    raise RuntimeError(
                        f"Neo4j created or matched fewer {rel_type} relationships than expected."
                    )

        with self._session() as session:
            session.execute_write(write_seed)

    def reset(self) -> None:
        """Remove only nodes and relationships tagged by this fraud dataset."""
        with self._session() as session:
            session.execute_write(
                lambda transaction: (
                    transaction.run(
                        "MATCH ()-[r]->() WHERE r.vexux_dataset = $dataset "
                        "DELETE r",
                        dataset=_DATASET_MARKER,
                    ).consume(),
                    transaction.run(
                        "MATCH (n) WHERE n.vexux_dataset = $dataset "
                        "OPTIONAL MATCH (n)-[r]-() "
                        "WITH n, collect(r) AS remaining "
                        "WHERE all(relationship IN remaining "
                        "WHERE relationship.vexux_dataset = $dataset) "
                        "DETACH DELETE n",
                        dataset=_DATASET_MARKER,
                    ).consume(),
                )
            )

    def counts(self) -> dict[str, int]:
        with self._session() as session:
            record = session.run(
                "MATCH (n) WHERE n.vexux_dataset = $dataset "
                "RETURN count(n) AS nodes",
                dataset=_DATASET_MARKER,
            ).single()
            relationship_record = session.run(
                "MATCH ()-[r]->() WHERE r.vexux_dataset = $dataset "
                "RETURN count(r) AS relationships",
                dataset=_DATASET_MARKER,
            ).single()
        return {
            "nodes": int(record["nodes"]) if record else 0,
            "relationships": int(relationship_record["relationships"])
            if relationship_record
            else 0,
        }
