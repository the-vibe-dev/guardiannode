"""Alert aggregation: repeated identical findings fold into one open alert.

A risky note sitting on screen gets re-captured and re-classified every time
anything else on the screen changes, which flooded the Risk Feed with dozens
of near-identical alerts. Instead of a new alert per frame, an open alert with
the same (device, profile, severity, categories) within the dedup window gets
its repeat_count bumped and its risk_id pointed at the newest RiskResult, so
the detail page always shows the latest evidence.

A change in severity or categories is a different finding and still creates a
fresh alert (escalations are never hidden inside a repeat counter).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Alert
from app.services.audit import log_action
from app.settings import settings

log = logging.getLogger(__name__)


def dedup_key(device_id: str | None, profile_id: str | None, severity: str, categories: list[str]) -> str:
    raw = "|".join([
        device_id or "",
        profile_id or "",
        severity,
        ",".join(sorted(set(categories or []))),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def upsert_alert(
    session: Session,
    *,
    risk_id: str,
    device_id: str | None,
    profile_id: str | None,
    severity: str,
    categories: list[str],
    source: str,
    source_ip: str | None = None,
    notify: bool = False,
    risk_summary: str = "",
) -> tuple[str, bool]:
    """Create an alert or fold into a recent identical open one.

    Returns (alert_id, created) — created is False when an existing alert
    absorbed this finding. When ``notify`` is set, sends email/webhook on the
    first occurrence (repeats don't re-notify).
    """
    now = datetime.now(timezone.utc)
    key = dedup_key(device_id, profile_id, severity, categories)
    window = timedelta(seconds=settings.alert_dedup_window_seconds)
    if window.total_seconds() > 0:
        cutoff = now - window
        existing = (
            session.query(Alert)
            .filter(
                Alert.dedup_key == key,
                Alert.status == "open",
                or_(Alert.last_seen_at >= cutoff, Alert.created_at >= cutoff),
            )
            .order_by(Alert.created_at.desc())
            .first()
        )
        if existing is not None:
            existing.repeat_count = (existing.repeat_count or 1) + 1
            existing.last_seen_at = now
            # Point at the newest risk so the detail page shows current evidence.
            existing.risk_id = risk_id
            log_action(
                session,
                actor="system",
                action="alert.repeat",
                target=existing.alert_id,
                details={"repeat_count": existing.repeat_count, "risk_id": risk_id, "source": source},
                source_ip=source_ip,
            )
            return existing.alert_id, False

    alert_id = str(ULID())
    alert = Alert(
        alert_id=alert_id,
        risk_id=risk_id,
        device_id=device_id,
        profile_id=profile_id,
        severity=severity,
        status="open",
        dedup_key=key,
        repeat_count=1,
        last_seen_at=now,
    )
    session.add(alert)
    log_action(
        session,
        actor="system",
        action="alert.create",
        target=alert_id,
        details={"severity": severity, "categories": categories, "source": source, "notify": notify},
        source_ip=source_ip,
    )
    if notify:
        # Email/webhook on the first occurrence only. Failures are logged and
        # never block the alert from being recorded.
        try:
            from app.services import notifications
            session.flush()
            notifications.dispatch(session, alert=alert, risk_summary=risk_summary, immediate=True)
        except Exception as e:  # pragma: no cover
            log.warning("alert notification failed: %s", e)
    return alert_id, True
