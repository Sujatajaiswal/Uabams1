from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.database import get_db
from app.services.retention import purge_expired_data

router = APIRouter(prefix="/api/v1", tags=["maintenance"])


@router.post("/maintenance/purge", response_model=schemas.PurgeResponse)
def purge(
    retention_days: int = Query(default=30, ge=1, description="Retention window in days (clause 6.4 default: 30)"),
    db: Session = Depends(get_db),
):
    """
    Deletes axle records, alerts, and sessions older than the retention
    window (clause 6.4: 30 days for space-domain data + alert reports).
    Intended to run as a scheduled job in production; exposed as an
    explicit endpoint here for auditability in this demo.
    """
    return purge_expired_data(db, retention_days=retention_days)


@router.get("/maintenance/notification-deliveries")
def notification_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.NotificationDelivery)
        .order_by(models.NotificationDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "alertId": row.alert_id,
            "channel": row.channel,
            "status": row.status,
            "recipient": row.recipient,
            "message": (
                row.request_payload.get("message")
                if isinstance(row.request_payload, dict)
                else None
            ),
            "providerMessageId": row.provider_message_id,
            "createdAt": row.created_at,
            "sentAt": row.sent_at,
            "errorMessage": row.error_message,
        }
        for row in rows
    ]


@router.get("/maintenance/tms-deliveries")
def tms_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.TmsDelivery)
        .order_by(models.TmsDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "days": row.days,
            "mode": row.mode,
            "status": row.status,
            "target": row.target,
            "fileName": row.file_name,
            "fileSizeBytes": row.file_size_bytes,
            "checksum": row.checksum,
            "createdAt": row.created_at,
            "deliveredAt": row.delivered_at,
            "errorMessage": row.error_message,
        }
        for row in rows
    ]
