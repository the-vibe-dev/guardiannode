"""Idempotent, timezone-aware family daily digests."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Alert, DigestRun, RiskResult, Setting
from app.services import consent, notifications


def family_timezone(session: Session) -> str:
    row = session.get(Setting, "family_timezone")
    return (row.value.strip() if row and row.value else "UTC") or "UTC"


def _notification_config(session: Session) -> dict:
    row = session.get(Setting, "notification_settings")
    if not row or not row.value:
        return {}
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _day_bounds(local_day: date, timezone: str) -> tuple[datetime, datetime]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {timezone}") from exc
    start = datetime.combine(local_day, time.min, tzinfo=zone)
    end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def build_summary(session: Session, *, local_day: date, timezone: str) -> dict:
    start, end = _day_bounds(local_day, timezone)
    alerts = (
        session.query(Alert)
        .filter(Alert.created_at >= start, Alert.created_at < end)
        .order_by(Alert.created_at.desc())
        .all()
    )
    counts = {level: 0 for level in ("critical", "high", "medium", "low")}
    for alert in alerts:
        counts[alert.severity] = counts.get(alert.severity, 0) + 1
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top = sorted(alerts, key=lambda item: (priority.get(item.severity, 9), -item.created_at.timestamp()))[:5]
    risks = {
        row.risk_id: row
        for row in session.query(RiskResult).filter(
            RiskResult.risk_id.in_([item.risk_id for item in top])
        ).all()
    } if top else {}
    # Deliberately excludes screenshots, OCR/text, summaries, URLs, titles, and app names.
    top_items = []
    for item in top:
        risk = risks.get(item.risk_id)
        top_items.append(
            {
                "alert_id": item.alert_id,
                "severity": item.severity,
                "categories": list((risk.categories if risk is not None else []) or []),
                "profile_id": item.profile_id,
                "created_at": item.created_at.isoformat(),
            }
        )
    return {
        "local_date": local_day.isoformat(),
        "timezone": timezone,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "counts": counts,
        "total": len(alerts),
        "top": top_items,
    }


def _body(summary: dict) -> str:
    counts = summary["counts"]
    lines = [
        f"GuardianNode daily digest for {summary['local_date']} ({summary['timezone']})",
        "",
        f"Total alerts: {summary['total']}",
        f"Critical: {counts.get('critical', 0)}",
        f"High: {counts.get('high', 0)}",
        f"Medium: {counts.get('medium', 0)}",
        f"Low: {counts.get('low', 0)}",
        "",
        "Open your local GuardianNode dashboard to review details.",
    ]
    return "\n".join(lines)


def _deliver(session: Session, run: DigestRun, *, now: datetime) -> DigestRun:
    """Persist a short delivery lease before network I/O, and retry only failures."""
    run.status = "processing"
    run.attempts = int(run.attempts or 0) + 1
    run.next_attempt_at = now + timedelta(minutes=10)
    session.commit()  # Never hold SQLite's write lock while waiting on SMTP.

    cfg = notifications._get_smtp_config(session)
    delivered = set(run.delivered_channels or [])
    outcomes = []
    if cfg and cfg.get("daily_digest_enabled", True) and cfg.get("host") and "email" not in delivered:
        ok, detail = notifications._send_email(
            cfg,
            f"[GuardianNode] Daily digest — {run.local_date}",
            _body(run.summary),
        )
        outcomes.append(("email", ok, detail))
        if ok:
            delivered.add("email")
            run.delivered_channels = sorted(delivered)
            session.commit()
    # A parent can disable this digest or notifications during SMTP delivery.
    cfg = notifications._get_smtp_config(session)
    if cfg and cfg.get("daily_digest_enabled", True) and cfg.get("webhook_url") and "webhook" not in delivered:
        ok, detail = notifications._send_webhook(
            cfg["webhook_url"],
            {
                "title": "GuardianNode daily digest",
                "message": _body(run.summary),
                "priority": "default",
                "severity": "digest",
            },
            allow_private=bool(cfg.get("webhook_allow_private", False)),
        )
        outcomes.append(("webhook", ok, detail))
        if ok:
            delivered.add("webhook")
            run.delivered_channels = sorted(delivered)
            session.commit()

    failures = [(channel, detail) for channel, ok, detail in outcomes if not ok]
    if failures:
        run.last_error = "; ".join(f"{channel}: {detail[:200]}" for channel, detail in failures)[:500]
        if run.attempts >= 5:
            run.status = "dead"
            run.next_attempt_at = None
            run.completed_at = now
        else:
            run.status = "retry"
            run.next_attempt_at = now + timedelta(seconds=notifications._retry_delay_seconds(run.attempts))
    else:
        run.status = "sent" if delivered else "dashboard_only"
        run.last_error = None
        run.next_attempt_at = None
        run.completed_at = now
    session.commit()
    return run


def run_due(session: Session, *, now: datetime | None = None) -> DigestRun | None:
    if not consent.choice_allowed(session, "notifications"):
        return None
    config = _notification_config(session)
    if not config.get("enabled") or not config.get("daily_digest_enabled", True):
        return None
    now = notifications._as_aware_utc(now) or datetime.now(UTC)
    # Retry a failed channel without creating a second daily record. A worker
    # killed during transport can resume after its finite processing lease.
    pending = session.query(DigestRun).filter(
        or_(
            and_(DigestRun.status == "retry", DigestRun.next_attempt_at <= now),
            and_(DigestRun.status == "processing", DigestRun.next_attempt_at <= now),
        )
    ).order_by(DigestRun.created_at.asc(), DigestRun.digest_id.asc()).first()
    if pending is not None:
        if pending.attempts >= 5:
            pending.status = "dead"
            pending.next_attempt_at = None
            pending.completed_at = now
            session.commit()
            return pending
        return _deliver(session, pending, now=now)

    timezone = family_timezone(session)
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        timezone = "UTC"
        zone = ZoneInfo("UTC")
    current = now.astimezone(zone)
    raw_time = str(config.get("daily_digest_time") or "08:00")
    try:
        hour, minute = (int(part) for part in raw_time.split(":", 1))
        scheduled = time(hour, minute)
    except (TypeError, ValueError):
        scheduled = time(8, 0)
    if current.timetz().replace(tzinfo=None) < scheduled:
        return None
    # The previous local calendar day is complete. Summarizing today's
    # midnight-to-08:00 slice would permanently omit the rest of today's alerts.
    local_day = current.date() - timedelta(days=1)
    existing = session.query(DigestRun).filter(
        DigestRun.local_date == local_day.isoformat(), DigestRun.timezone == timezone
    ).first()
    if existing is not None:
        return None
    run = DigestRun(
        digest_id=str(ULID()),
        local_date=local_day.isoformat(),
        timezone=timezone,
        status="queued",
        summary=build_summary(session, local_day=local_day, timezone=timezone),
    )
    session.add(run)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return None
    return _deliver(session, run, now=now)
