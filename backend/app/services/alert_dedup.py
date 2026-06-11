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
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Alert
from app.services.audit import log_action
from app.settings import settings


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
) -> tuple[str, bool]:
    """Create an alert or fold into a recent identical open one.

    Returns (alert_id, created) — created is False when an existing alert
    absorbed this finding.
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
    session.add(Alert(
        alert_id=alert_id,
        risk_id=risk_id,
        device_id=device_id,
        profile_id=profile_id,
        severity=severity,
        status="open",
        dedup_key=key,
        repeat_count=1,
        last_seen_at=now,
    ))
    log_action(
        session,
        actor="system",
        action="alert.create",
        target=alert_id,
        details={"severity": severity, "categories": categories, "source": source},
        source_ip=source_ip,
    )
    return alert_id, True
