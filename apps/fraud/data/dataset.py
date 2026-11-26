"""Canonical deterministic fraud dataset shared by local data stores."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any


_CUSTOMER_NAMES = (
    "Alice Smith",
    "Bob Jones",
    "Carol Patel",
    "David Chen",
    "Evan Brooks",
    "Farah Khan",
    "Grace Miller",
    "Hugo Silva",
    "Imani Reed",
    "Jonas Weber",
)
_MERCHANTS = (
    ("M7001", "Northwind Electronics", "high"),
    ("M7002", "Green Market", "normal"),
    ("M7003", "Rapid Digital Goods", "medium"),
    ("M7004", "Silverline Travel", "normal"),
    ("M7005", "Vertex Mobile", "high"),
    ("M7006", "Harbor Pharmacy", "normal"),
)
_TRANSACTION_COUNTS = (5, 4, 6, 5, 6, 5, 5, 5, 5, 4)
_ACCOUNT_IDS = (
    ("A1001", "A1002"),
    ("A1003", "A1013"),
    ("A1004", "A1014"),
    ("A1005", "A1015"),
    ("A1006", "A1007"),
    ("A1008", "A1016"),
    ("A1009",),
    ("A1010",),
    ("A1011",),
    ("A1012",),
)
_ALERTS = (
    ("C1001", 0, "shared_device", "high", "open"),
    ("C1001", 1, "transaction_velocity", "high", "open"),
    ("C1002", 5, "shared_device_review", "low", "closed"),
    ("C1003", 9, "watchlist_merchant", "medium", "closed"),
    ("C1005", 20, "transaction_velocity", "high", "open"),
    ("C1005", 21, "high_value_activity", "high", "open"),
    ("C1006", 26, "reversal_pattern", "medium", "closed"),
    ("C1008", 36, "merchant_review", "low", "closed"),
    ("C1009", 41, "watchlist_merchant", "medium", "open"),
    ("C1010", 46, "unusual_location", "low", "closed"),
    ("C1004", 15, "merchant_review", "low", "closed"),
    ("C1007", 31, "account_review", "medium", "closed"),
)
_INVESTIGATIONS = (
    ("C1001", "open"),
    ("C1003", "monitoring"),
    ("C1005", "open"),
    ("C1006", "closed"),
    ("C1008", "monitoring"),
    ("C1009", "open"),
)
_CITIES = ("London", "Manchester", "Birmingham", "Leeds", "Bristol", "Glasgow", "Cardiff", "Liverpool")


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def generate_fraud_dataset(
    customer_count: int = 10,
    seed: int = 2026,
) -> dict[str, Any]:
    """Return stable SQLite rows and graph entities/relationships for one run."""
    if customer_count < len(_CUSTOMER_NAMES):
        raise ValueError("customer_count must be at least 10.")
    if not isinstance(seed, int):
        raise TypeError("seed must be an integer.")

    rng = random.Random(seed)
    customers = []
    accounts = []
    devices_by_id = {}
    addresses = []
    customer_devices = []
    customer_addresses = []
    for index in range(customer_count):
        sequence = index + 1
        customer_id = f"C{1000 + sequence}"
        if index < len(_CUSTOMER_NAMES):
            name = _CUSTOMER_NAMES[index]
        else:
            name = f"Customer {sequence:04d}"
        risk = ("high", "normal", "medium", "normal", "high", "medium", "normal", "normal", "medium", "normal")[index % 10]
        customers.append({
            "customer_id": customer_id,
            "full_name": name,
            "risk_level": risk,
            "created_at": "2024-01-01T00:00:00+00:00",
        })

        if index < len(_ACCOUNT_IDS):
            customer_account_ids = _ACCOUNT_IDS[index]
        else:
            customer_account_ids = (f"A{1016 + index - len(_ACCOUNT_IDS) + 1:04d}",)
        for account_number, account_id in enumerate(customer_account_ids):
            accounts.append({
                "account_id": account_id,
                "customer_id": customer_id,
                "account_status": "frozen" if index == 2 and account_number == 0 else "active",
                "opened_at": _timestamp(datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(days=index * 37 + account_number * 18)),
            })

        device_id = "D5001" if index < 2 else f"D{5000 + sequence:04d}"
        device = devices_by_id.setdefault(device_id, {
            "device_id": device_id,
            "device_type": ("mobile", "web", "tablet")[index % 3],
            "risk_level": "high" if index < 2 else "normal",
        })
        if index < 2:
            device["risk_level"] = "high"
        address_id = f"ADDR{8000 + sequence:04d}"
        addresses.append({
            "address_id": address_id,
            "city": _CITIES[index % len(_CITIES)],
            "country": "GB",
        })
        customer_devices.append({"customer_id": customer_id, "device_id": device_id})
        customer_addresses.append({"customer_id": customer_id, "address_id": address_id})

    merchants = [
        {
            "merchant_id": merchant_id,
            "merchant_name": name,
            "risk_level": risk,
        }
        for merchant_id, name, risk in _MERCHANTS
    ]

    transactions = []
    transaction_number = 0
    start = datetime(2025, 1, 10, 10, 15, tzinfo=timezone.utc)
    accounts_by_customer = {
        row["customer_id"]: [
            account["account_id"] for account in accounts
            if account["customer_id"] == row["customer_id"]
        ]
        for row in customers
    }
    for index, customer in enumerate(customers):
        customer_id = customer["customer_id"]
        count = (
            _TRANSACTION_COUNTS[index]
            if index < len(_TRANSACTION_COUNTS)
            else 4 + (index % 3)
        )
        account_ids = accounts_by_customer[customer_id]
        for offset in range(count):
            transaction_number += 1
            merchant = _MERCHANTS[(transaction_number + index) % len(_MERCHANTS)]
            if index == 0 and offset < 2:
                merchant = _MERCHANTS[0]
            amount = (
                (1299.99, 1180.00, 45.60, 65.00, 35.50)[offset]
                if index == 0
                else (62.10, 118.25, 39.90, 25.00)[offset]
                if index == 1
                else round(rng.uniform(18.0, 950.0), 2)
            )
            occurred_at = start + timedelta(minutes=transaction_number * 17)
            transaction = {
                "transaction_id": f"T{11000 + transaction_number:05d}",
                "account_id": account_ids[offset % len(account_ids)],
                "customer_id": customer_id,
                "merchant_id": merchant[0],
                "amount": amount,
                "currency": "GBP",
                "occurred_at": _timestamp(occurred_at),
                "status": "declined" if index >= 2 and offset == count - 1 and index % 4 == 2 else "approved",
            }
            transactions.append(transaction)

    fraud_cases = []
    investigations = []
    investigation_events = []
    for index, (customer_id, status) in enumerate(_INVESTIGATIONS, start=1):
        case_id = f"F{9000 + index}"
        investigation_id = f"INV{3000 + index}"
        fraud_cases.append({
            "fraud_case_id": case_id,
            "customer_id": customer_id,
            "status": "open" if status == "open" else "monitoring" if status == "monitoring" else "closed",
            "severity": "high" if customer_id in {"C1001", "C1005"} else "medium",
        })
        opened_at = _timestamp(datetime(2025, 1, 11, tzinfo=timezone.utc) + timedelta(days=index))
        investigations.append({
            "investigation_id": investigation_id,
            "customer_id": customer_id,
            "fraud_case_id": case_id,
            "status": status,
            "assigned_to": "investigator",
            "opened_at": opened_at,
            "closed_at": opened_at if status == "closed" else None,
        })
        investigation_events.append({
            "investigation_id": investigation_id,
            "event_type": "opened",
            "event_payload": {"actor": "investigator", "status": status},
            "created_at": opened_at,
        })

    fraud_alerts = []
    for index, (customer_id, transaction_index, alert_type, severity, status) in enumerate(_ALERTS, start=1):
        transaction = transactions[transaction_index]
        fraud_alerts.append({
            "alert_id": f"ALERT{6000 + index}",
            "customer_id": customer_id,
            "transaction_id": transaction["transaction_id"],
            "alert_type": alert_type,
            "severity": severity,
            "status": status,
            "created_at": _timestamp(datetime.fromisoformat(transaction["occurred_at"]) + timedelta(minutes=5)),
        })
    for index in range(10, customer_count):
        customer_id = customers[index]["customer_id"]
        transaction = next(row for row in transactions if row["customer_id"] == customer_id)
        fraud_alerts.append({
            "alert_id": f"ALERT{6000 + len(fraud_alerts) + 1}",
            "customer_id": customer_id,
            "transaction_id": transaction["transaction_id"],
            "alert_type": "account_review",
            "severity": "low",
            "status": "closed",
            "created_at": _timestamp(datetime.fromisoformat(transaction["occurred_at"]) + timedelta(minutes=5)),
        })

    graph_nodes = []
    graph_relationships = []

    def add_nodes(label: str, rows: list[dict[str, Any]], id_key: str) -> None:
        for row in rows:
            properties = dict(row)
            node_id = str(properties.pop(id_key))
            properties[id_key] = node_id
            if label == "Customer":
                properties["name"] = properties["full_name"]
                properties["risk"] = properties["risk_level"]
            if label == "FraudCase":
                properties["case_id"] = node_id
            graph_nodes.append({
                "id": node_id,
                "label": label,
                "properties": {"id": node_id, **properties},
            })

    def add_relationship(source: str, target: str, rel_type: str, rel_id: str) -> None:
        graph_relationships.append({
            "id": rel_id,
            "source": source,
            "target": target,
            "type": rel_type,
            "properties": {},
        })

    add_nodes("Customer", customers, "customer_id")
    add_nodes("Account", accounts, "account_id")
    add_nodes("Device", list(devices_by_id.values()), "device_id")
    add_nodes("Address", addresses, "address_id")
    add_nodes("Merchant", merchants, "merchant_id")
    add_nodes("Transaction", transactions, "transaction_id")
    add_nodes("FraudCase", fraud_cases, "fraud_case_id")
    add_nodes("FraudAlert", fraud_alerts, "alert_id")
    for account in accounts:
        add_relationship(account["customer_id"], account["account_id"], "OWNS", f"owns:{account['account_id']}")
    for transaction in transactions:
        add_relationship(transaction["account_id"], transaction["transaction_id"], "HAS_TRANSACTION", f"transaction:{transaction['transaction_id']}")
        add_relationship(transaction["transaction_id"], transaction["merchant_id"], "INVOLVES", f"merchant:{transaction['transaction_id']}")
    for row in customer_devices:
        add_relationship(row["customer_id"], row["device_id"], "USES", f"device:{row['customer_id']}")
    for row in customer_addresses:
        add_relationship(row["customer_id"], row["address_id"], "LIVES_AT", f"address:{row['customer_id']}")
    for investigation in investigations:
        add_relationship(investigation["customer_id"], investigation["fraud_case_id"], "INVOLVED_IN", f"case:{investigation['investigation_id']}")
    for alert in fraud_alerts:
        add_relationship(alert["customer_id"], alert["alert_id"], "HAS_ALERT", f"alert:{alert['alert_id']}")
        add_relationship(alert["alert_id"], alert["transaction_id"], "GENERATED_BY", f"generated:{alert['alert_id']}")
    add_relationship("C1001", "C1002", "SHARES_DEVICE_WITH", "shared-device:C1001:C1002")

    return {
        "seed": seed,
        "customers": customers,
        "merchants": merchants,
        "accounts": accounts,
        "transactions": transactions,
        "devices": list(devices_by_id.values()),
        "addresses": addresses,
        "customer_devices": customer_devices,
        "customer_addresses": customer_addresses,
        "fraud_cases": fraud_cases,
        "fraud_alerts": fraud_alerts,
        "investigations": investigations,
        "investigation_events": investigation_events,
        "graph_nodes": graph_nodes,
        "graph_relationships": graph_relationships,
    }
