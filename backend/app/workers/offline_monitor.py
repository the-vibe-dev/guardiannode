"""Detect when a child device stops reporting and alert the parent.

A child who is a local administrator can end the agent from Task Manager or
shut the PC down. The Windows watchdog service auto-restarts the agent, but if
the machine is off — or the agent can't come back — the backend simply stops
receiving heartbeats. This worker turns that silence into a visible alert so
the parent is told that monitoring stopped, rather than assuming "no alerts =
all clear".

Reconnection clears the state automatically: the heartbeat/event paths set the
device back to ``online`` and update ``last_seen``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Alert, Device, Event, RiskResult
from app.db.session import get_sessionmaker
from app.services.audit import log_action
from app.services.device_state import is_device_paused
from app.settings import settings

log = logging.getLogger(__name__)

_OFFLINE_CATEGORY = "monitoring_gap"


def _ulid() -> str:
    return str(ULID())


def _raise_offline_alert(session: Session, device: Device, silent_seconds: int) -> str:
    """Synthesize an event+risk+alert so the offline event shows in the feed
    and flows through the normal notification path."""
    now = datetime.now(UTC)
    summary = (
        f"Monitoring stopped on {device.hostname}: no data received for "
        f"{silent_seconds // 60} min. The device may be off, offline, or the "
        f"agent was closed."
    )
    event = Event(
        event_id=_ulid(),
        device_id=device.device_id,
        source_type="system",
        app_name="GuardianNode",
        window_title="Monitoring status",
        timestamp=now,
        received_at=now,
        evidence_type="system",
    )
    session.add(event)
    session.flush()
    risk = RiskResult(
        risk_id=_ulid(),
        event_id=event.event_id,
        risk_level="high",
        score=70,
        categories=[_OFFLINE_CATEGORY],
        summary=summary,
        evidence=[],
        recommended_action="check_device",
        rules_triggered=["monitoring_offline"],
        confidence=1.0,
    )
    session.add(risk)
    session.flush()
    alert = Alert(
        alert_id=_ulid(),
        risk_id=risk.risk_id,
        device_id=device.device_id,
        profile_id=None,
        severity="high",
        status="open",
        repeat_count=1,
        last_seen_at=now,
    )
    session.add(alert)
    session.flush()
    log_action(
        session,
        actor="system",
        action="device.offline",
        target=device.device_id,
        details={"hostname": device.hostname, "silent_seconds": silent_seconds},
    )
    try:
        from app.services import notifications
        notifications.enqueue(session, alert=alert, risk_summary=summary, immediate=True)
    except Exception as e:  # notification enqueue failures must not block the alert
        log.warning("offline-alert notification enqueue failed: %s", e)
    return alert.alert_id


def check_once(session: Session, *, now: datetime | None = None) -> list[str]:
    """Mark silent devices offline and alert once per offline transition.

    Returns the device_ids newly transitioned to offline.
    """
    if not settings.device_offline_alert_enabled:
        return []
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.device_offline_after_seconds)
    transitioned: list[str] = []
    devices = (
        session.query(Device)
        .filter(Device.paired.is_(True), Device.status.notin_(["offline", "paused", "disabled"]))
        .all()
    )
    for device in devices:
        # Honor an active pause without flagging it as a tamper gap.
        if is_device_paused(device, now=now):
            continue
        last = device.last_seen
        if last is None:
            continue
        # Normalize naive timestamps (SQLite) to UTC for comparison.
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last >= cutoff:
            continue
        silent_seconds = int((now - last).total_seconds())
        device.status = "offline"
        _raise_offline_alert(session, device, silent_seconds)
        transitioned.append(device.device_id)
        log.info("device %s (%s) marked offline after %ds silent",
                 device.device_id, device.hostname, silent_seconds)
    if transitioned:
        session.commit()
    return transitioned


def run_once() -> list[str]:
    db = get_sessionmaker()()
    try:
        return check_once(db)
    finally:
        db.close()


async def loop() -> None:
    interval = max(15, int(settings.device_offline_check_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(run_once)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("offline monitor failed: %s", e)
