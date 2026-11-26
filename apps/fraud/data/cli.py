"""Initialize and seed local SQLite and Neo4j fraud data stores."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from apps.fraud.data.dataset import generate_fraud_dataset
from apps.fraud.data.neo4j_store import Neo4jFraudStore
from apps.fraud.data.paths import fraud_database_path
from apps.fraud.data.sqlite_store import SQLiteFraudRepository


def _sqlite_path(config: Any):
    return fraud_database_path(config.sql_database_path)


def _neo4j_store(config: Any) -> tuple[Any, Neo4jFraudStore]:
    if not config.neo4j_uri or not config.neo4j_username or not config.neo4j_password:
        raise ValueError(
            "NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD must be configured "
            "to seed or reset fraud graph data."
        )
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Neo4j support requires the already-installed 'neo4j' package."
        ) from exc
    driver = GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_username, config.neo4j_password),
    )
    store = Neo4jFraudStore(driver, config.neo4j_database)
    try:
        store.verify_connection()
        store.initialize_schema()
    except Exception:
        driver.close()
        raise
    return driver, store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-sqlite", help="create the SQLite fraud schema")
    for name in ("seed", "reset"):
        command = commands.add_parser(name, help=f"{name} the canonical fraud dataset")
        command.add_argument("--customer-count", type=int, default=10)
        command.add_argument("--seed", type=int, default=2026)
        if name == "reset":
            command.add_argument(
                "--confirm-reset",
                action="store_true",
                help="confirm deletion of Vexux fraud rows/nodes in both stores",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from core.config import get_config

    config = get_config()
    repository = SQLiteFraudRepository(_sqlite_path(config))
    if args.command == "init-sqlite":
        repository.initialize()
        repository.require_initialized()
        print(f"SQLite fraud schema initialized at {repository.database_path}")
        return 0

    if args.command == "reset" and not args.confirm_reset:
        raise ValueError("Reset requires the explicit --confirm-reset option.")
    if args.customer_count < 2:
        raise ValueError("--customer-count must be at least 2.")
    dataset = generate_fraud_dataset(
        customer_count=args.customer_count,
        seed=args.seed,
    )
    repository.require_initialized()
    driver, graph_store = _neo4j_store(config)
    try:
        if args.command == "reset":
            repository.reset()
            try:
                graph_store.reset()
            except Exception as exc:
                raise RuntimeError(
                    "SQLite fraud data was reset, but Neo4j reset failed. "
                    "Correct the Neo4j issue and rerun reset with --confirm-reset."
                ) from exc
        try:
            repository.seed(dataset)
        except Exception as exc:
            raise RuntimeError(
                "SQLite fraud seeding failed; Neo4j was not seeded. "
                "Correct the SQLite issue and safely rerun the same command."
            ) from exc
        try:
            graph_store.seed(dataset)
        except Exception as exc:
            raise RuntimeError(
                "SQLite fraud data was seeded, but Neo4j seeding failed. "
                "Both stores may now be partially seeded; correct the Neo4j issue "
                "and safely rerun the same command."
            ) from exc
        print(f"SQLite rows: {repository.counts()}")
        print(f"Neo4j app-owned entities: {graph_store.counts()}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"Fraud data command failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
