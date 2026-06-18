"""
Centralised application settings, read from environment variables.
Keeping this in one place makes the Render / Docker / local configurations
explicit and easy to audit.
"""
import os
from pathlib import Path
from tempfile import gettempdir


def _database_url() -> str:
    default_db = Path(gettempdir()) / "uabams-cloud" / "uabams.db"
    url = os.getenv("DATABASE_URL", f"sqlite:///{default_db.as_posix()}")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Settings:
    DATABASE_URL: str = _database_url()
    ARCHIVE_STORAGE_DIR: str = os.getenv(
        "ARCHIVE_STORAGE_DIR",
        str(Path(gettempdir()) / "uabams-cloud" / "archives"),
    )
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    DEFAULT_SAMPLING_RATE: int = int(os.getenv("DEFAULT_SAMPLING_RATE", "2500"))
    GATEWAY_OFFLINE_AFTER_SECONDS: int = int(
        os.getenv("GATEWAY_OFFLINE_AFTER_SECONDS", "300")
    )
    SEED_ON_STARTUP: bool = os.getenv("SEED_ON_STARTUP", "true").lower() == "true"

    # Default acceleration thresholds (g) applied when a route has no
    # explicit entry in the threshold table yet.
    DEFAULT_VERTICAL_THRESHOLD: float = 50.0
    DEFAULT_LATERAL_THRESHOLD: float = 80.0
    DEFAULT_ROUTE: str = "Bangalore-Chennai"

    # Module 3 rule: alerts only fire at or above this speed (km/h)
    ALERT_SPEED_GATE_KMPH: float = 80.0

    # Optional production integrations. Without these values, the system
    # records an auditable outbox/delivery row instead of pretending to send.
    ALERT_NOTIFICATION_WEBHOOK_URL: str = os.getenv("ALERT_NOTIFICATION_WEBHOOK_URL", "")
    ALERT_NOTIFICATION_BEARER_TOKEN: str = os.getenv("ALERT_NOTIFICATION_BEARER_TOKEN", "")
    TMS_DELIVERY_MODE: str = os.getenv("TMS_DELIVERY_MODE", "local").lower()
    TMS_HTTP_URL: str = os.getenv("TMS_HTTP_URL", "")
    TMS_HTTP_BEARER_TOKEN: str = os.getenv("TMS_HTTP_BEARER_TOKEN", "")
    TMS_LOCAL_EXPORT_DIR: str = os.getenv(
        "TMS_LOCAL_EXPORT_DIR",
        str(Path(gettempdir()) / "uabams-cloud" / "tms-exports"),
    )


settings = Settings()
