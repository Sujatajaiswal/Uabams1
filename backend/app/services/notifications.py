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


def _sms_text(alert: models.Alert, session: models.GatewaySession | None) -> str:
    gps = ""
    if session:
        gps = f" GPS={session.lat:.6f},{session.lon:.6f}"
    return (
        f"UABAMS {alert.severity}: {alert.metric} {alert.value:.1f}g "
        f"> {alert.threshold_value:.1f}g, train={alert.train_id}, "
        f"route={alert.route}, axle={alert.axle_id or '-'}, "
        f"speed={alert.speed_kmph:.1f}km/h{gps}"
    )


def _sms_payload(alert: models.Alert, session: models.GatewaySession | None) -> dict:
    recipients = [
        item.strip()
        for item in settings.SMS_RECIPIENTS.split(",")
        if item.strip()
    ]
    return {
        "to": recipients,
        "message": _sms_text(alert, session),
        "alert": _payload_for_alert(alert, session),
    }


def _post_json(url: str, payload: dict, bearer_token: str = "") -> tuple[str, datetime | None, dict | None, str | None]:
    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        status = "sent" if response.is_success else "failed"
        sent_at = datetime.utcnow() if response.is_success else None
        response_payload = {
            "status_code": response.status_code,
            "body": response.text[:1000],
        }
        return status, sent_at, response_payload, None
    except Exception as exc:  # pragma: no cover - network/provider dependent
        return "failed", None, None, str(exc)[:512]


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
    sms_url = settings.SMS_SERVER_URL.strip()

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
            status, sent_at, response_payload, error = _post_json(
                webhook_url,
                payload,
                settings.ALERT_NOTIFICATION_BEARER_TOKEN,
            )
            delivery.status = status
            delivery.sent_at = sent_at
            delivery.response_payload = response_payload
            delivery.error_message = error

        deliveries.append(delivery)

        sms_payload = _sms_payload(alert, session)
        sms_delivery = models.NotificationDelivery(
            alert_id=alert.id,
            channel="sms" if sms_url else "sms_outbox",
            recipient=",".join(sms_payload["to"]) or None,
            status="queued",
            request_payload=sms_payload,
        )
        db.add(sms_delivery)
        db.flush()

        if sms_url:
            status, sent_at, response_payload, error = _post_json(
                sms_url,
                sms_payload,
                settings.SMS_SERVER_BEARER_TOKEN,
            )
            sms_delivery.status = status
            sms_delivery.sent_at = sent_at
            sms_delivery.response_payload = response_payload
            sms_delivery.error_message = error

        deliveries.append(sms_delivery)

    return deliveries
