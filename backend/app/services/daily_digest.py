"""Idempotent, timezone-aware family daily digests."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Alert, DigestRun, RiskResult, Setting
from app.services import notifications


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


def run_due(session: Session, *, now: datetime | None = None) -> DigestRun | None:
    config = _notification_config(session)
    if not config.get("enabled") or not config.get("daily_digest_enabled", True):
        return None
    timezone = family_timezone(session)
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        timezone = "UTC"
        zone = ZoneInfo("UTC")
    current = (now or datetime.now(UTC)).astimezone(zone)
    raw_time = str(config.get("daily_digest_time") or "08:00")
    try:
        hour, minute = (int(part) for part in raw_time.split(":", 1))
        scheduled = time(hour, minute)
    except (TypeError, ValueError):
        scheduled = time(8, 0)
    if current.timetz().replace(tzinfo=None) < scheduled:
        return None
    local_day = current.date()
    existing = session.query(DigestRun).filter(
        DigestRun.local_date == local_day.isoformat(), DigestRun.timezone == timezone
    ).first()
    if existing is not None:
        return None
    run = DigestRun(
        digest_id=str(ULID()),
        local_date=local_day.isoformat(),
        timezone=timezone,
        status="processing",
        summary=build_summary(session, local_day=local_day, timezone=timezone),
    )
    session.add(run)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return None

    outcomes = []
    cfg = notifications._get_smtp_config(session)
    if cfg and cfg.get("host"):
        outcomes.append(notifications._send_email(
            cfg,
            f"[GuardianNode] Daily digest — {local_day.isoformat()}",
            _body(run.summary),
        ))
    if cfg and cfg.get("webhook_url"):
        outcomes.append(notifications._send_webhook(
            cfg["webhook_url"],
            {
                "title": "GuardianNode daily digest",
                "message": _body(run.summary),
                "priority": "default",
                "severity": "digest",
            },
            allow_private=bool(cfg.get("webhook_allow_private", False)),
        ))
    run.status = "sent" if all(ok for ok, _detail in outcomes) else "error"
    if not outcomes:
        run.status = "dashboard_only"
    run.completed_at = datetime.now(UTC)
    session.commit()
    return run
