"""SQLite schema and idempotent persistence for the fraud application."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


_SCHEMA_VERSION = 1
_APPLICATION_ID = 0x56585558
_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('normal', 'medium', 'high')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id TEXT PRIMARY KEY,
    merchant_name TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('normal', 'medium', 'high'))
);
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_status TEXT NOT NULL CHECK (account_status IN ('active', 'frozen', 'closed')),
    opened_at TEXT NOT NULL,
    UNIQUE (account_id, customer_id)
);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id),
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'declined', 'reversed')),
    FOREIGN KEY (account_id, customer_id)
        REFERENCES accounts(account_id, customer_id),
    UNIQUE (transaction_id, customer_id)
);
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    device_type TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('normal', 'medium', 'high'))
);
CREATE TABLE IF NOT EXISTS addresses (
    address_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    country TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_devices (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    PRIMARY KEY (customer_id, device_id)
);
CREATE TABLE IF NOT EXISTS customer_addresses (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    address_id TEXT NOT NULL REFERENCES addresses(address_id),
    PRIMARY KEY (customer_id, address_id)
);
CREATE TABLE IF NOT EXISTS fraud_cases (
    fraud_case_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL CHECK (status IN ('open', 'monitoring', 'closed')),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    UNIQUE (fraud_case_id, customer_id)
);
CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    transaction_id TEXT,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (transaction_id, customer_id)
        REFERENCES transactions(transaction_id, customer_id)
);
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    fraud_case_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'monitoring', 'closed')),
    assigned_to TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY (fraud_case_id, customer_id)
        REFERENCES fraud_cases(fraud_case_id, customer_id)
);
CREATE TABLE IF NOT EXISTS investigation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    event_type TEXT NOT NULL,
    event_payload TEXT NOT NULL CHECK (json_valid(event_payload)),
    created_at TEXT NOT NULL,
    UNIQUE (investigation_id, event_type, created_at)
);
CREATE TABLE IF NOT EXISTS fraud_dataset_metadata (
    dataset_name TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    customer_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_customer
    ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_customer_time
    ON transactions(customer_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_transactions_account_time
    ON transactions(account_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_alert_customer_status
    ON fraud_alerts(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_alert_transaction
    ON fraud_alerts(transaction_id);
CREATE INDEX IF NOT EXISTS idx_investigation_customer_status
    ON investigations(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_event_investigation_time
    ON investigation_events(investigation_id, created_at);
"""
_REQUIRED_TABLES = frozenset({
    "customers",
    "merchants",
    "accounts",
    "transactions",
    "devices",
    "addresses",
    "customer_devices",
    "customer_addresses",
    "fraud_cases",
    "fraud_alerts",
    "investigations",
    "investigation_events",
    "fraud_dataset_metadata",
})
_DELETE_ORDER = (
    "investigation_events",
    "investigations",
    "fraud_alerts",
    "fraud_cases",
    "transactions",
    "customer_addresses",
    "customer_devices",
    "accounts",
    "devices",
    "addresses",
    "merchants",
    "customers",
    "fraud_dataset_metadata",
)


class SQLiteFraudRepository:
    """Own only the fraud-specific tables in a local SQLite database."""

    def __init__(self, database_path: str | Path):
        if not str(database_path).strip():
            raise ValueError("SQLite fraud database path must not be empty.")
        self.database_path = Path(database_path).expanduser()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(self.database_path), timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise RuntimeError("SQLite fraud database operation failed.") from exc
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            try:
                application_id = int(
                    connection.execute("PRAGMA application_id").fetchone()[0]
                )
                if application_id not in {0, _APPLICATION_ID}:
                    raise RuntimeError(
                        "The configured SQLite file belongs to another application."
                    )
                existing_tables = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                if application_id == 0 and existing_tables - {"sqlite_sequence"}:
                    raise RuntimeError(
                        "Refusing to initialize fraud data in a non-empty SQLite file "
                        "that is not owned by the fraud application."
                    )
                connection.executescript(
                    "BEGIN;\n"
                    + _SCHEMA
                    + f"\nPRAGMA application_id={_APPLICATION_ID};\n"
                    + f"\nPRAGMA user_version={_SCHEMA_VERSION};\nCOMMIT;"
                )
            except (sqlite3.Error, RuntimeError) as exc:
                if connection.in_transaction:
                    connection.rollback()
                if isinstance(exc, RuntimeError):
                    raise
                raise RuntimeError("Could not initialize the SQLite fraud schema.") from exc

    def require_initialized(self) -> None:
        if not self.database_path.is_file():
            raise FileNotFoundError(
                "Fraud SQLite database is missing. Run "
                "'python -m apps.fraud.data.cli init-sqlite' before starting real mode."
            )
        with self.connect() as connection:
            application_id = int(
                connection.execute("PRAGMA application_id").fetchone()[0]
            )
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
            missing = sorted(_REQUIRED_TABLES - tables)
            if application_id != _APPLICATION_ID:
                raise RuntimeError(
                    "SQLite file is not initialized as a Vexux fraud database. "
                    "Use a dedicated fraud database path and run init-sqlite."
                )
            if missing:
                raise RuntimeError(
                    "Fraud SQLite schema is not initialized; missing tables: "
                    + ", ".join(missing)
                    + ". Run 'python -m apps.fraud.data.cli init-sqlite'."
                )

    def require_seeded(self) -> None:
        self.require_initialized()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT customer_id FROM customers WHERE customer_id = 'C1001'"
            ).fetchone()
            metadata = connection.execute(
                "SELECT dataset_name FROM fraud_dataset_metadata "
                "WHERE dataset_name = 'canonical'"
            ).fetchone()
        if row is None or metadata is None:
            raise RuntimeError(
                "The canonical SQLite fraud dataset is not present. "
                "Run 'python -m apps.fraud.data.cli seed' before starting real mode."
            )

    def seed(self, dataset: dict[str, Any]) -> None:
        self.require_initialized()
        with self.connect() as connection:
            for table, rows, columns in (
                ("customers", dataset["customers"], ("customer_id", "full_name", "risk_level", "created_at")),
                ("merchants", dataset["merchants"], ("merchant_id", "merchant_name", "risk_level")),
                ("accounts", dataset["accounts"], ("account_id", "customer_id", "account_status", "opened_at")),
                ("transactions", dataset["transactions"], ("transaction_id", "account_id", "customer_id", "merchant_id", "amount", "currency", "occurred_at", "status")),
                ("devices", dataset["devices"], ("device_id", "device_type", "risk_level")),
                ("addresses", dataset["addresses"], ("address_id", "city", "country")),
                ("customer_devices", dataset["customer_devices"], ("customer_id", "device_id")),
                ("customer_addresses", dataset["customer_addresses"], ("customer_id", "address_id")),
                ("fraud_cases", dataset["fraud_cases"], ("fraud_case_id", "customer_id", "status", "severity")),
                ("fraud_alerts", dataset["fraud_alerts"], ("alert_id", "customer_id", "transaction_id", "alert_type", "severity", "status", "created_at")),
                ("investigations", dataset["investigations"], ("investigation_id", "customer_id", "fraud_case_id", "status", "assigned_to", "opened_at", "closed_at")),
            ):
                self._upsert_rows(
                    connection,
                    table,
                    columns,
                    rows,
                    ignore_duplicates=table in {"customer_devices", "customer_addresses"},
                )

            for event in dataset["investigation_events"]:
                connection.execute(
                    """
                    INSERT INTO investigation_events
                        (investigation_id, event_type, event_payload, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(investigation_id, event_type, created_at) DO UPDATE SET
                        event_payload = excluded.event_payload,
                        created_at = excluded.created_at
                    """,
                    (
                        event["investigation_id"],
                        event["event_type"],
                        json.dumps(event["event_payload"], sort_keys=True),
                        event["created_at"],
                    ),
                )
            connection.execute(
                """
                INSERT INTO fraud_dataset_metadata
                    (dataset_name, seed, customer_count, generated_at)
                VALUES ('canonical', ?, ?, ?)
                ON CONFLICT(dataset_name) DO UPDATE SET
                    seed = excluded.seed,
                    customer_count = excluded.customer_count,
                    generated_at = excluded.generated_at
                """,
                (
                    dataset["seed"],
                    len(dataset["customers"]),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )

    @staticmethod
    def _upsert_rows(
        connection: sqlite3.Connection,
        table: str,
        columns: tuple[str, ...],
        rows: list[dict[str, Any]],
        *,
        ignore_duplicates: bool = False,
    ) -> None:
        if not rows:
            return
        names = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{column} = excluded.{column}" for column in columns[1:]
        )
        conflict_clause = (
            "INSERT OR IGNORE"
            if ignore_duplicates
            else f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
                 f"ON CONFLICT({columns[0]}) DO UPDATE SET {updates}"
        )
        if ignore_duplicates:
            statement = (
                f"{conflict_clause} INTO {table} ({names}) VALUES ({placeholders})"
            )
        else:
            statement = conflict_clause
        connection.executemany(
            statement,
            [tuple(row[column] for column in columns) for row in rows],
        )

    def reset(self) -> None:
        """Delete only the fraud application's tables, in FK-safe order."""
        self.require_initialized()
        with self.connect() as connection:
            for table in _DELETE_ORDER:
                connection.execute(f"DELETE FROM {table}")

    def counts(self) -> dict[str, int]:
        self.require_initialized()
        with self.connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in sorted(_REQUIRED_TABLES)
            }
