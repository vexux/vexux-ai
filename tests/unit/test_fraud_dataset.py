from __future__ import annotations

import re
from pathlib import Path


FRAUD_DATA = Path(__file__).parents[2] / "apps" / "fraud" / "data"
MYSQL_SEED = (FRAUD_DATA / "mysql" / "seed.sql").read_text(encoding="utf-8")
NEO4J_SEED = (FRAUD_DATA / "neo4j" / "seed.cypher").read_text(encoding="utf-8")


def _insert_block(table: str) -> str:
    match = re.search(
        rf"INSERT INTO {table}\b.*?VALUES(.*?)(?:ON DUPLICATE KEY UPDATE|;)",
        MYSQL_SEED,
        re.DOTALL,
    )
    assert match is not None, f"Missing fixture inserts for {table}"
    return match.group(1)


def _ids(block: str, prefix: str) -> list[str]:
    return re.findall(rf"'({prefix}\d+)'", block)


def test_mysql_fraud_seed_has_expected_entity_counts_and_unique_ids():
    expected_counts = {
        "customers": ("C", 10),
        "merchants": ("M", 6),
        "accounts": ("A", 16),
        "transactions": ("T", 50),
        "fraud_alerts": ("ALERT", 12),
        "investigations": ("INV", 6),
    }
    blocks = {}
    for table, (prefix, expected_count) in expected_counts.items():
        block = _insert_block(table)
        entity_ids = _ids(block, prefix)
        assert len(entity_ids) == expected_count
        assert len(entity_ids) == len(set(entity_ids))
        blocks[table] = block

    customer_ids = set(_ids(blocks["customers"], "C"))
    merchant_ids = set(_ids(blocks["merchants"], "M"))
    account_rows = re.findall(r"\('(A\d+)', '(C\d+)'", blocks["accounts"])
    transaction_rows = re.findall(
        r"\('(T\d+)', '(A\d+)', '(C\d+)', '(M\d+)'",
        blocks["transactions"],
    )
    account_owners = {account_id: customer_id for account_id, customer_id in account_rows}
    assert len(account_rows) == 16
    assert all(customer_id in customer_ids for _, customer_id in account_rows)
    assert len(transaction_rows) == 50
    assert all(
        account_id in {row[0] for row in account_rows}
        and account_owners[account_id] == customer_id
        and customer_id in customer_ids
        and merchant_id in merchant_ids
        for _, account_id, customer_id, merchant_id in transaction_rows
    )

    alert_rows = re.findall(
        r"\('(ALERT\d+)', '(C\d+)', (?:NULL|'(T\d+)')",
        blocks["fraud_alerts"],
    )
    assert len(alert_rows) == 12
    transactions_by_id = {
        transaction_id: (account_id, customer_id)
        for transaction_id, account_id, customer_id, _ in transaction_rows
    }
    assert all(
        customer_id in customer_ids
        and (
            not transaction_id
            or (
                transaction_id in transactions_by_id
                and transactions_by_id[transaction_id][1] == customer_id
                and account_owners[transactions_by_id[transaction_id][0]] == customer_id
            )
        )
        for _, customer_id, transaction_id in alert_rows
    )
    investigation_rows = re.findall(
        r"\('(INV\d+)', '(C\d+)', '(F\d+)'",
        blocks["investigations"],
    )
    case_node_block = re.search(
        r"UNWIND \[(.*?)\] AS row\s+MERGE \(n:FraudCase ",
        NEO4J_SEED,
        re.DOTALL,
    )
    assert len(investigation_rows) == 6
    assert case_node_block is not None
    case_ids = set(re.findall(r"\{id: '(F\d+)'", case_node_block.group(1)))
    assert all(
        customer_id in customer_ids and case_id in case_ids
        for _, customer_id, case_id in investigation_rows
    )


def test_neo4j_seed_has_valid_entity_ranges_and_bounded_relationships():
    expected_ranges = {
        "Customer": (8, 12),
        "Account": (15, 25),
        "Device": (8, 15),
        "Merchant": (6, 10),
        "Address": (6, 10),
        "FraudCase": (4, 8),
        "FraudAlert": (12, 25),
    }
    node_blocks = {
        label: block
        for block, label in re.findall(
            r"UNWIND \[(.*?)\] AS row\s+MERGE \(n:(\w+) ",
            NEO4J_SEED,
            re.DOTALL,
        )
    }
    for label, (minimum, maximum) in expected_ranges.items():
        assert label in node_blocks, f"Missing {label} graph fixtures"
        node_ids = re.findall(r"\{id: '([^']+)'", node_blocks[label])
        assert minimum <= len(node_ids) <= maximum
        assert len(node_ids) == len(set(node_ids))

    relationship_merges = re.findall(
        r"MERGE \((\w+)\)-\[:[A-Z_]+\]->\((\w+)\)", NEO4J_SEED
    )
    assert len(relationship_merges) == 40
    for statement in NEO4J_SEED.split(";"):
        matched_variables = set(re.findall(r"\((\w+):\w+ \{id:", statement))
        relationship_variables = {
            variable
            for relationship in re.findall(
                r"MERGE \((\w+)\)-\[:[A-Z_]+\]->\((\w+)\)", statement
            )
            for variable in relationship
        }
        assert relationship_variables <= matched_variables
    assert "MERGE (c1)-[:SHARES_DEVICE_WITH]->(c2)" in NEO4J_SEED
    assert "MERGE (c7)-[:USES]->(d6)" in NEO4J_SEED
    assert "MERGE (c2)-[:SHARES_ADDRESS_WITH]->(c3)" in NEO4J_SEED


def test_demo_sql_fixture_has_valid_references():
    demo_sql = (FRAUD_DATA / "sqlite" / "demo.sql").read_text(encoding="utf-8")
    connection_ids = set(re.findall(r"'(A\d+)'", demo_sql))
    transaction_ids = set(re.findall(r"'(T\d+)'", demo_sql))
    assert "A100" in connection_ids
    assert "T1001" in transaction_ids
    assert "'C1001'" in demo_sql
