from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.config import settings
from app.database import get_db
from app.services.notifications import queue_or_send_alert_notifications
from app.services.retention import purge_expired_data

router = APIRouter(prefix="/api/v1", tags=["maintenance"])


def _is_demo_sms() -> bool:
    return settings.SMS_SERVER_URL.strip().lower() in {"demo", "internal://demo", "demo://sms"}


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
        .order_by(models.NotificationDelivery.created_at.desc(), models.NotificationDelivery.id.desc())
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


@router.get("/maintenance/integration-status")
def integration_status(db: Session = Depends(get_db)):
    latest_sms = (
        db.query(models.NotificationDelivery)
        .filter(models.NotificationDelivery.channel.in_(["sms", "sms_outbox"]))
        .order_by(models.NotificationDelivery.created_at.desc())
        .first()
    )
    return {
        "authentication": {
            "apiAuthEnabled": bool(settings.API_AUTH_TOKEN),
            "gatewayAuthEnabled": bool(settings.GATEWAY_API_TOKEN),
            "operatorHeader": "Authorization: Bearer <API_AUTH_TOKEN>",
            "gatewayHeader": "Authorization: Bearer <GATEWAY_API_TOKEN>",
        },
        "smsServer": {
            "configured": bool(settings.SMS_SERVER_URL.strip()),
            "mode": "demo" if _is_demo_sms() else ("http" if settings.SMS_SERVER_URL.strip() else "outbox"),
            "recipientCount": len([r for r in settings.SMS_RECIPIENTS.split(",") if r.strip()]),
            "outputTable": "notification_deliveries",
            "latestStatus": latest_sms.status if latest_sms else None,
            "latestMessage": (
                latest_sms.request_payload.get("message")
                if latest_sms and isinstance(latest_sms.request_payload, dict)
                else None
            ),
        },
        "database": {
            "type": "postgresql" if settings.DATABASE_URL.startswith("postgresql") else "sqlite",
            "notificationDeliveries": db.query(func.count(models.NotificationDelivery.id)).scalar() or 0,
        },
    }


@router.post("/maintenance/demo-sms")
def send_demo_sms(db: Session = Depends(get_db)):
    """
    Creates a demo threshold alert and sends it through the configured SMS path.
    With SMS_SERVER_URL=demo, this marks the SMS as sent and stores the demo
    provider message id in notification_deliveries.
    """
    now = datetime.utcnow()
    gateway = db.get(models.Gateway, "GW_SMS_DEMO")
    if gateway is None:
        gateway = models.Gateway(gateway_id="GW_SMS_DEMO", status="online")
        db.add(gateway)

    gateway.status = "online"
    gateway.last_seen_at = now
    gateway.last_upload_at = now

    session = models.GatewaySession(
        session_id=f"SMS-DEMO-{now.strftime('%Y%m%d%H%M%S%f')}",
        gateway_id="GW_SMS_DEMO",
        train_id="TRAIN_SMS_DEMO",
        route="Bangalore-Chennai",
        timestamp=now,
        lat=13.158,
        lon=77.732,
        speed_kmph=105.0,
        raw_payload={"source": "maintenance/demo-sms"},
    )
    db.add(session)
    db.flush()

    alert = models.Alert(
        session_id=session.id,
        gateway_id=session.gateway_id,
        train_id=session.train_id,
        route=session.route,
        axle_id="AX01",
        metric="vertical",
        value=77.2,
        threshold_value=50.0,
        speed_kmph=session.speed_kmph,
        severity="Warning",
        message="Demo SMS alert: vertical acceleration exceeded route threshold",
        nearest_track_feature_km=75.0,
        created_at=now,
    )
    db.add(alert)
    db.flush()

    deliveries = queue_or_send_alert_notifications(db, [alert], session)
    db.commit()

    sms_delivery = next((row for row in deliveries if row.channel in {"sms", "sms_outbox"}), deliveries[-1])
    return {
        "ok": True,
        "alertId": alert.id,
        "channel": sms_delivery.channel,
        "status": sms_delivery.status,
        "recipient": sms_delivery.recipient,
        "message": (
            sms_delivery.request_payload.get("message")
            if isinstance(sms_delivery.request_payload, dict)
            else None
        ),
        "providerMessageId": sms_delivery.provider_message_id,
        "outputTable": "notification_deliveries",
        "createdAt": sms_delivery.created_at,
        "sentAt": sms_delivery.sent_at,
    }


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
