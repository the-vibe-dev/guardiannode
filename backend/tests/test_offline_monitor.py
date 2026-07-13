"""Offline/tamper detection raises one alert per offline transition."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Alert, Device
from app.workers import offline_monitor


def _device(db, *, last_seen_delta_s: int, status="online", paused_delta_s=None) -> Device:
    now = datetime.now(UTC)
    d = Device(
        device_id="dev1", hostname="kid-pc", platform="windows", paired=True,
        status=status, last_seen=now - timedelta(seconds=last_seen_delta_s),
        paused_until=(now + timedelta(seconds=paused_delta_s)) if paused_delta_s else None,
    )
    db.add(d)
    db.flush()
    return d


def test_silent_device_raises_offline_alert(db_session):
    _device(db_session, last_seen_delta_s=600)
    transitioned = offline_monitor.check_once(db_session)
    assert transitioned == ["dev1"]
    assert db_session.get(Device, "dev1").status == "offline"
    alerts = db_session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "high"


def test_recent_heartbeat_does_not_alert(db_session):
    _device(db_session, last_seen_delta_s=30)
    assert offline_monitor.check_once(db_session) == []
    assert db_session.query(Alert).count() == 0


def test_offline_alert_is_raised_once_not_repeatedly(db_session):
    _device(db_session, last_seen_delta_s=600)
    offline_monitor.check_once(db_session)
    # Second pass: device already offline, so no new alert.
    assert offline_monitor.check_once(db_session) == []
    assert db_session.query(Alert).count() == 1


def test_paused_device_is_not_flagged(db_session):
    _device(db_session, last_seen_delta_s=600, status="paused", paused_delta_s=3600)
    assert offline_monitor.check_once(db_session) == []
    assert db_session.query(Alert).count() == 0
