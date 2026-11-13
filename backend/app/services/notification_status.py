"""Parent-only delivery diagnostics without notification contents or secrets."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.db.models import DigestRun, NotificationJob, NotificationLog, Setting
from app.services import consent, notifications


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def delivery_status(session: Session) -> dict:
    """Return bounded, metadata-only diagnostics; never perform a delivery."""
    row = session.get(Setting, "notification_settings")
    try:
        config = json.loads(row.value) if row and row.value else {}
    except (TypeError, ValueError):
        config = {}
    if not isinstance(config, dict):
        config = {}

    counts = dict.fromkeys(("queued", "retry", "processing", "sent", "dead", "skipped"), 0)
    for status, total in session.query(
        NotificationJob.status, func.count(NotificationJob.id)
    ).group_by(NotificationJob.status).all():
        if status in counts:
            counts[status] = total

    successes: dict[str, datetime] = {channel: created for channel, created in session.query(
        NotificationLog.channel, func.max(NotificationLog.created_at)
    ).filter(
        NotificationLog.channel.in_(("email", "webhook")),
        NotificationLog.result == "ok",
    ).group_by(NotificationLog.channel).all()}

    # Explicit field allowlists prevent a future model field (or arbitrary
    # transport exception) from disclosing evidence or a token-bearing URL.
    jobs = session.query(NotificationJob).order_by(
        NotificationJob.created_at.desc(), NotificationJob.id.desc()
    ).limit(20).all()
    attempts = session.query(NotificationLog).filter(
        NotificationLog.channel.in_(("email", "webhook")),
    ).order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc()).limit(20).all()
    digest = session.query(DigestRun).order_by(
        DigestRun.created_at.desc(), DigestRun.digest_id.desc()
    ).first()

    return {
        "enabled": bool(config.get("enabled", False)) and consent.choice_allowed(session, "notifications"),
        "consent_allowed": consent.choice_allowed(session, "notifications"),
        "worker_enabled": settings_mod.settings.notification_worker_enabled,
        "routing": {
            "immediate_min_severity": notifications.immediate_min_severity(session),
            "protected_safety_floor": "high",
            "rechecks_current_policy": True,
            "historical_backfill": False,
        },
        "channels": {
            "email": {
                "configured": bool(config.get("host")),
                "last_success_at": _timestamp(successes.get("email")),
            },
            "webhook": {
                "configured": bool(config.get("webhook_url")),
                "last_success_at": _timestamp(successes.get("webhook")),
            },
        },
        "counts": counts,
        "recent_jobs": [
            {
                "id": job.id,
                "alert_id": job.alert_id,
                "severity": job.severity,
                "status": job.status,
                "attempts": job.attempts,
                "skip_reason": "current_policy" if job.last_error == notifications.POLICY_SUPPRESSED else None,
                "next_attempt_at": _timestamp(job.next_attempt_at),
                "created_at": _timestamp(job.created_at),
                "updated_at": _timestamp(job.updated_at),
                "delivered_channels": [
                    channel for channel in (job.delivered_channels or [])
                    if channel in {"email", "webhook"}
                ],
            }
            for job in jobs
        ],
        "recent_attempts": [
            {
                "id": attempt.id,
                "alert_id": attempt.alert_id,
                "channel": attempt.channel,
                "severity": attempt.severity,
                "result": attempt.result,
                "created_at": _timestamp(attempt.created_at),
            }
            for attempt in attempts
        ],
        "last_digest": {
            "local_date": digest.local_date,
            "timezone": digest.timezone,
            "status": digest.status,
            "total_alerts": (digest.summary or {}).get("total", 0),
            "completed_at": _timestamp(digest.completed_at),
        } if digest else None,
    }
