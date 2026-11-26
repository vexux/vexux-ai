"""Default local paths for fraud-specific generated data."""

from pathlib import Path


DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent
    / "generated"
    / "vexux_fraud.db"
)


def fraud_database_path(configured_path: str | None = None) -> Path:
    return Path(configured_path or DEFAULT_DATABASE_PATH).expanduser()
