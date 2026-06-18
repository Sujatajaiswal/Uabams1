"""Alert notification outbox and optional webhook sender."""
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app import models
from app.config import settings


def _payload_for_alert(alert: models.Alert, session: models.GatewaySession | None) -> dict:
    return {
        "alertId": alert.id,
        "gatewayId": alert.gateway_id,
        "trainId": alert.train_id,
        "route": alert.route,
        "axleId": alert.axle_id,
        "metric": alert.metric,
        "valueG": alert.value,
        "thresholdG": alert.threshold_value,
        "speedKmph": alert.speed_kmph,
        "severity": alert.severity,
        "message": alert.message,
        "nearestTrackFeatureKm": alert.nearest_track_feature_km,
        "timestamp": alert.created_at.isoformat() if alert.created_at else None,
        "gps": {
            "lat": session.lat,
            "lon": session.lon,
        } if session else None,
    }


def queue_or_send_alert_notifications(
    db: Session,
    alerts: list[models.Alert],
    session: models.GatewaySession,
) -> list[models.NotificationDelivery]:
    """
    Creates one auditable notification row per alert. If a notification
    webhook is configured, sends immediately; otherwise leaves the row queued.
    """
    deliveries: list[models.NotificationDelivery] = []
    webhook_url = settings.ALERT_NOTIFICATION_WEBHOOK_URL.strip()

    for alert in alerts:
        payload = _payload_for_alert(alert, session)
        delivery = models.NotificationDelivery(
            alert_id=alert.id,
            channel="webhook" if webhook_url else "outbox",
            status="queued",
            request_payload=payload,
        )
        db.add(delivery)
        db.flush()

        if webhook_url:
            headers = {}
            if settings.ALERT_NOTIFICATION_BEARER_TOKEN:
                headers["Authorization"] = f"Bearer {settings.ALERT_NOTIFICATION_BEARER_TOKEN}"
            try:
                response = httpx.post(webhook_url, json=payload, headers=headers, timeout=10)
                delivery.status = "sent" if response.is_success else "failed"
                delivery.sent_at = datetime.utcnow() if response.is_success else None
                delivery.response_payload = {
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                }
            except Exception as exc:  # pragma: no cover - network/provider dependent
                delivery.status = "failed"
                delivery.error_message = str(exc)[:512]

        deliveries.append(delivery)

    return deliveries
