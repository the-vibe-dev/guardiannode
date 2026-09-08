from __future__ import annotations

import json
from datetime import UTC, date, datetime

from app.db.models import Alert, Device, DigestRun, Event, RiskResult, Setting
from app.services import daily_digest


def test_digest_day_bounds_follow_dst_transition():
    start, end = daily_digest._day_bounds(date(2026, 11, 1), "America/New_York")
    assert (end - start).total_seconds() == 25 * 60 * 60


def test_daily_digest_is_idempotent_and_excludes_evidence_content(db_session):
    db_session.add(Setting(
        key="notification_settings",
        value=json.dumps({
            "enabled": True,
            "daily_digest_enabled": True,
            "daily_digest_time": "08:00",
        }),
    ))
    db_session.add(Setting(key="family_timezone", value="America/New_York"))
    db_session.add(Device(device_id="device-1", hostname="kid-pc", paired=True))
    db_session.flush()
    db_session.add(Event(
        event_id="event-1",
        device_id="device-1",
        source_type="visible_text",
        app_name="private-app.exe",
        window_title="private title",
        url="https://private.example/path",
        timestamp=datetime(2026, 8, 17, 13, tzinfo=UTC),
    ))
    db_session.flush()
    db_session.add(RiskResult(
        risk_id="risk-1",
        event_id="event-1",
        risk_level="high",
        score=90,
        categories=["grooming"],
        summary="private OCR summary",
    ))
    db_session.flush()
    db_session.add(Alert(
        alert_id="alert-1",
        risk_id="risk-1",
        device_id="device-1",
        severity="high",
        created_at=datetime(2026, 8, 17, 13, tzinfo=UTC),
    ))
    db_session.commit()

    now = datetime(2026, 8, 17, 13, 30, tzinfo=UTC)
    first = daily_digest.run_due(db_session, now=now)
    second = daily_digest.run_due(db_session, now=now)

    assert first is not None and first.status == "dashboard_only"
    assert second is None
    assert db_session.query(DigestRun).count() == 1
    encoded = json.dumps(first.summary)
    for sensitive in (
        "private-app.exe", "private title", "private.example", "private OCR summary"
    ):
        assert sensitive not in encoded
