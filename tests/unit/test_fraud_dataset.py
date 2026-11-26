import json
import sqlite3

import pytest

from apps.fraud.data.dataset import generate_fraud_dataset
from apps.fraud.data.sqlite_store import SQLiteFraudRepository
from apps.fraud.investigation import FraudInvestigationService
from apps.fraud.policy import FraudPolicy
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.registry import KnowledgeSourceRegistry
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend


def test_canonical_dataset_is_reproducible_and_preserves_required_scenarios():
    dataset = generate_fraud_dataset()
    assert dataset == generate_fraud_dataset()
    assert len(dataset["customers"]) == 10
    assert len(dataset["accounts"]) == 16
    assert len(dataset["transactions"]) == 50
    assert len(dataset["fraud_alerts"]) == 12
    assert len(dataset["investigations"]) == 6

    transactions_by_customer = {}
    for transaction in dataset["transactions"]:
        transactions_by_customer.setdefault(transaction["customer_id"], []).append(transaction)
    assert len(transactions_by_customer["C1001"]) == 5
    assert len(transactions_by_customer["C1002"]) == 4

    alice_alerts = [
        alert for alert in dataset["fraud_alerts"]
        if alert["customer_id"] == "C1001"
    ]
    assert len(alice_alerts) == 2
    assert all(
        alert["severity"] == "high" and alert["status"] == "open"
        for alert in alice_alerts
    )
    bob_alerts = [
        alert for alert in dataset["fraud_alerts"]
        if alert["customer_id"] == "C1002"
    ]
    assert len(bob_alerts) == 1
    assert bob_alerts[0]["severity"] == "low"
    assert bob_alerts[0]["status"] == "closed"
    assert {
        relationship["type"]
        for relationship in dataset["graph_relationships"]
        if relationship["source"] == "C1001" and relationship["target"] == "C1002"
    } == {"SHARES_DEVICE_WITH"}


def test_canonical_dataset_references_are_consistent():
    dataset = generate_fraud_dataset()
    customers = {row["customer_id"] for row in dataset["customers"]}
    merchants = {row["merchant_id"] for row in dataset["merchants"]}
    accounts = {
        row["account_id"]: row["customer_id"] for row in dataset["accounts"]
    }
    transactions = {
        row["transaction_id"]: row for row in dataset["transactions"]
    }
    assert all(
        transaction["customer_id"] in customers
        and transaction["merchant_id"] in merchants
        and accounts[transaction["account_id"]] == transaction["customer_id"]
        for transaction in dataset["transactions"]
    )
    assert all(
        alert["customer_id"] in customers
        and transactions[alert["transaction_id"]]["customer_id"] == alert["customer_id"]
        for alert in dataset["fraud_alerts"]
    )
    assert all(
        investigation["customer_id"] in customers
        for investigation in dataset["investigations"]
    )


def test_sqlite_seed_is_idempotent_enforces_foreign_keys_and_serializes_events(tmp_path):
    database = tmp_path / "fraud.db"
    repository = SQLiteFraudRepository(database)
    repository.initialize()
    repository.require_initialized()
    dataset = generate_fraud_dataset()

    repository.seed(dataset)
    first_counts = repository.counts()
    repository.seed(dataset)

    assert repository.counts() == first_counts
    assert first_counts["customers"] == 10
    assert first_counts["transactions"] == 50
    with repository.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        events = connection.execute(
            "SELECT event_payload FROM investigation_events"
        ).fetchall()
        assert json.loads(events[0][0])["actor"] == "investigator"
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO accounts VALUES ('A9999', 'C9999', 'active', '2025-01-01')"
            )

    repository.require_seeded()


def test_sqlite_reset_only_deletes_fraud_owned_tables(tmp_path):
    database = tmp_path / "fraud.db"
    repository = SQLiteFraudRepository(database)
    repository.initialize()
    repository.seed(generate_fraud_dataset())
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated_records (value TEXT)")
        connection.execute("INSERT INTO unrelated_records VALUES ('preserve me')")

    repository.reset()

    assert all(count == 0 for count in repository.counts().values())
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM unrelated_records"
        ).fetchone()[0] == "preserve me"


def test_sqlite_store_reports_missing_schema_and_seed(tmp_path):
    repository = SQLiteFraudRepository(tmp_path / "fraud.db")
    with pytest.raises(FileNotFoundError, match="init-sqlite"):
        repository.require_initialized()

    repository.initialize()
    with pytest.raises(RuntimeError, match="canonical SQLite fraud dataset"):
        repository.require_seeded()


def test_sqlite_initialization_refuses_a_non_fraud_database(tmp_path):
    database = tmp_path / "existing.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE business_records (id INTEGER PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="non-empty SQLite file"):
        SQLiteFraudRepository(database).initialize()


def test_generated_sqlite_and_graph_fixtures_preserve_deterministic_risk(tmp_path):
    dataset = generate_fraud_dataset()
    repository = SQLiteFraudRepository(tmp_path / "fraud.db")
    repository.initialize()
    repository.seed(dataset)

    graphs = KnowledgeGraphRegistry()
    for name in ("customer_graph", "fraud_graph"):
        graph = InMemoryKnowledgeGraph()
        graph.name = name
        for node in dataset["graph_nodes"]:
            graph.add_node(
                node["id"],
                label=node["label"],
                properties=node["properties"],
            )
        for relationship in dataset["graph_relationships"]:
            graph.add_relationship(
                relationship["source"],
                relationship["target"],
                relationship["type"],
                properties=relationship["properties"],
                rel_id=relationship["id"],
            )
        graphs.register(graph)

    sources = KnowledgeSourceRegistry()
    source = SQLKnowledgeSource(SQLiteBackend(str(repository.database_path)))
    source.name = "business_db"
    sources.register(source)
    service = FraudInvestigationService(graphs, sources, FraudPolicy())

    alice = service.investigate("C1001", actor="investigator")
    bob = service.investigate("C1002", actor="investigator")

    assert alice.risk_assessment == "high"
    assert alice.metadata["transaction_count"] == 5
    assert alice.metadata["alert_count"] == 2
    assert bob.risk_assessment == "medium"
    assert bob.metadata["transaction_count"] == 4
    assert bob.metadata["alert_count"] == 1
    assert "shared_device_relationship" in bob.contributing_signals


def test_dataset_rejects_invalid_size_and_seed_type():
    with pytest.raises(ValueError, match="at least 10"):
        generate_fraud_dataset(customer_count=9)
    with pytest.raises(TypeError, match="seed must be an integer"):
        generate_fraud_dataset(seed="not-an-integer")
