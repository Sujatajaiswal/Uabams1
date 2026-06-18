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


def ensure_gateway_columns() -> None:
    existing = _column_names("gateways")
    if not existing:
        return

    statements: list[str] = []
    if "status" not in existing:
        statements.append(
            "ALTER TABLE gateways ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'offline'"
        )
    if "last_seen_at" not in existing:
        statements.append("ALTER TABLE gateways ADD COLUMN last_seen_at TIMESTAMP")
    if "last_upload_at" not in existing:
        statements.append("ALTER TABLE gateways ADD COLUMN last_upload_at TIMESTAMP")
    if "created_at" not in existing:
        statements.append(
            "ALTER TABLE gateways ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_schema_compatibility() -> None:
    ensure_gateway_columns()
