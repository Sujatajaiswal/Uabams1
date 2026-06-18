"""CRIS/TMS delivery service with auditable local and HTTP modes."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.tms_export import build_tms_export_zip


def deliver_tms_export(db: Session, days: int = 30) -> models.TmsDelivery:
    """
    Build the TMS ZIP and deliver it according to configuration.

    Modes:
      - local: write the ZIP to TMS_LOCAL_EXPORT_DIR.
      - http: POST the ZIP bytes to TMS_HTTP_URL.

    Until CRIS provides the final protocol/credentials, local mode gives an
    auditable hand-off artifact and HTTP mode is ready for API-based transfer.
    """
    zip_bytes = build_tms_export_zip(db, days=days)
    checksum = sha256(zip_bytes).hexdigest()
    file_name = f"uabams_tms_export_{days}d_{datetime.utcnow():%Y%m%d_%H%M%S}.zip"
    mode = settings.TMS_DELIVERY_MODE

    delivery = models.TmsDelivery(
        days=days,
        mode=mode,
        status="created",
        target=settings.TMS_HTTP_URL if mode == "http" else settings.TMS_LOCAL_EXPORT_DIR,
        file_name=file_name,
        file_size_bytes=len(zip_bytes),
        checksum=checksum,
    )
    db.add(delivery)
    db.flush()

    if mode == "http":
        if not settings.TMS_HTTP_URL:
            delivery.status = "failed"
            delivery.error_message = "TMS_HTTP_URL is required when TMS_DELIVERY_MODE=http"
            return delivery

        headers = {
            "Content-Type": "application/zip",
            "X-UABAMS-Filename": file_name,
            "X-UABAMS-SHA256": checksum,
        }
        if settings.TMS_HTTP_BEARER_TOKEN:
            headers["Authorization"] = f"Bearer {settings.TMS_HTTP_BEARER_TOKEN}"

        try:
            response = httpx.post(
                settings.TMS_HTTP_URL,
                content=zip_bytes,
                headers=headers,
                timeout=60,
            )
            delivery.status = "delivered" if response.is_success else "failed"
            delivery.delivered_at = datetime.utcnow() if response.is_success else None
            delivery.response_payload = {
                "status_code": response.status_code,
                "body": response.text[:1000],
            }
        except Exception as exc:  # pragma: no cover - network/provider dependent
            delivery.status = "failed"
            delivery.error_message = str(exc)[:512]
        return delivery

    if mode != "local":
        delivery.status = "failed"
        delivery.error_message = f"Unsupported TMS_DELIVERY_MODE '{mode}'"
        return delivery

    target_dir = Path(settings.TMS_LOCAL_EXPORT_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    target_path.write_bytes(zip_bytes)
    delivery.status = "delivered"
    delivery.delivered_at = datetime.utcnow()
    delivery.target = str(target_path)
    delivery.response_payload = {"path": str(target_path)}
    return delivery
