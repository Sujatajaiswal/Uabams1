"""
Data retention per the RDSO spec and the gateway ICD.

Working parsed data older than the configured window can be purged from
query tables. Original ZIP archives and extracted raw/binary artifacts are
not deleted here: ICD section 12.6 requires permanent retention of the
authoritative archive and unchanged extracted binary files.

In production this would run as a daily scheduled job (e.g. a Render cron
job or APScheduler). It's exposed here as an explicit, auditable endpoint
instead, since silently deleting data on a timer is a much bigger surprise
to bake into a demo than an operator-triggered action.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models


def purge_expired_data(db: Session, retention_days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    expired_sessions = (
        db.query(models.GatewaySession)
        .filter(models.GatewaySession.timestamp < cutoff)
        .all()
    )
    session_ids = [s.id for s in expired_sessions]

    axle_deleted = 0
    alerts_deleted = 0
    if session_ids:
        db.query(models.RmsRecord).filter(
            models.RmsRecord.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.PeakRecord).filter(
            models.PeakRecord.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.FaultRecord).filter(
            models.FaultRecord.session_id.in_(session_ids)
        ).delete(synchronize_session=False)

        axle_deleted = (
            db.query(models.AxleRecord)
            .filter(models.AxleRecord.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
        alerts_deleted = (
            db.query(models.Alert)
            .filter(models.Alert.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )

    sessions_deleted = (
        db.query(models.GatewaySession)
        .filter(models.GatewaySession.timestamp < cutoff)
        .delete(synchronize_session=False)
    )

    db.commit()
    return {
        "cutoffDate": cutoff,
        "sessionsDeleted": sessions_deleted,
        "axleRecordsDeleted": axle_deleted,
        "alertsDeleted": alerts_deleted,
    }
