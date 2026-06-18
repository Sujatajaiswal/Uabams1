"""Small additive schema upgrades for demo/Render databases.

SQLAlchemy's create_all() creates missing tables, but it intentionally does
not alter tables that already exist. Render already had a PostgreSQL database
with an older `gateways` table, so the app must add newly required columns
before the API starts querying them.
"""
from sqlalchemy import inspect, text

from app.database import engine


def _column_names(table_name: str) -> set[str]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_missing_columns(table_name: str, definitions: dict[str, str]) -> None:
    existing = _column_names(table_name)
    if not existing:
        return

    statements: list[str] = []
    for column_name, sql_definition in definitions.items():
        if column_name not in existing:
            statements.append(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {sql_definition}'
            )

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_schema_compatibility() -> None:
    _add_missing_columns("gateways", {
        "status": "VARCHAR(16) NOT NULL DEFAULT 'offline'",
        "last_seen_at": "TIMESTAMP",
        "last_upload_at": "TIMESTAMP",
        "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    })
    _add_missing_columns("gateway_sessions", {
        "session_id": "VARCHAR(64)",
        "gateway_id": "VARCHAR(64)",
        "train_id": "VARCHAR(64)",
        "route": "VARCHAR(128) NOT NULL DEFAULT 'Bangalore-Chennai'",
        "timestamp": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "lat": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "lon": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "speed_kmph": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "raw_payload": "JSON",
        "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    })
    _add_missing_columns("axle_records", {
        "session_id": "INTEGER",
        "axle_id": "VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN'",
        "vertical_g": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "lateral_g": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "rms": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "peak": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    })
    _add_missing_columns("alerts", {
        "session_id": "INTEGER",
        "gateway_id": "VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN'",
        "train_id": "VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN'",
        "route": "VARCHAR(128) NOT NULL DEFAULT 'Unknown'",
        "axle_id": "VARCHAR(32)",
        "metric": "VARCHAR(16) NOT NULL DEFAULT 'vertical'",
        "value": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "threshold_value": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "speed_kmph": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        "severity": "VARCHAR(16) NOT NULL DEFAULT 'Info'",
        "message": "VARCHAR(255) NOT NULL DEFAULT 'Legacy alert'",
        "nearest_track_feature_km": "DOUBLE PRECISION",
        "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    })
