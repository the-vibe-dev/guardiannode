from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import Alert, Device, DigestRun, Event, RiskResult, Setting
from app.services import daily_digest, notifications


def test_digest_day_bounds_follow_dst_transition():
    start, end = daily_digest._day_bounds(date(2026, 11, 1), "America/New_York")
    assert (end - start).total_seconds() == 25 * 60 * 60


@pytest.mark.parametrize("toggle", ["enabled", "daily_digest_enabled"])
def test_digest_rechecks_enablement_between_channels(db_session, monkeypatch, toggle):
    _config(db_session, host="smtp.example.test", webhook_url="https://notify.example.test/hook")

    def email(*args):
        with Session(bind=db_session.get_bind()) as other:
            row = other.get(Setting, "notification_settings")
            config = json.loads(row.value)
            config[toggle] = False
            row.value = json.dumps(config)
            other.commit()
        return True, "ok"

    monkeypatch.setattr(notifications, "_send_email", email)
    monkeypatch.setattr(notifications, "_send_webhook", lambda *args, **kwargs: pytest.fail("Disabled digest sent a second channel"))
    run = daily_digest.run_due(db_session, now=datetime(2026, 11, 2, 10, tzinfo=UTC))
    assert run.status == "sent"
    assert run.delivered_channels == ["email"]


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

    now = datetime(2026, 8, 18, 13, 30, tzinfo=UTC)
    first = daily_digest.run_due(db_session, now=now)
    second = daily_digest.run_due(db_session, now=now)

    assert first is not None and first.status == "dashboard_only"
    assert second is None
    assert db_session.query(DigestRun).count() == 1
    assert first.local_date == "2026-08-17"
    assert first.summary["total"] == 1
    encoded = json.dumps(first.summary)
    for sensitive in (
        "private-app.exe", "private title", "private.example", "private OCR summary"
    ):
        assert sensitive not in encoded


def _config(db, **values):
    db.add(Setting(key="notification_settings", value=json.dumps({
        "enabled": True, "daily_digest_enabled": True, "daily_digest_time": "08:00", **values,
    })))
    db.commit()


def test_digest_covers_completed_local_day_at_dst_boundary(db_session):
    _config(db_session)
    db_session.add(Setting(key="family_timezone", value="America/New_York"))
    db_session.commit()
    run = daily_digest.run_due(db_session, now=datetime(2026, 11, 2, 13, tzinfo=UTC))
    assert run.local_date == "2026-11-01"
    start = datetime.fromisoformat(run.summary["window_start"])
    end = datetime.fromisoformat(run.summary["window_end"])
    assert (end - start).total_seconds() == 25 * 3600
    assert end == datetime(2026, 11, 2, 5, tzinfo=UTC)


def test_digest_retries_only_failed_channel_after_restart(db_session, monkeypatch):
    _config(db_session, host="smtp.example.test", webhook_url="https://notify.example.test/hook")
    sent = []
    results = iter([(False, "temporary failure"), (True, "ok")])
    monkeypatch.setattr(notifications, "_send_email", lambda *a: (sent.append("email") or (True, "ok")))
    monkeypatch.setattr(notifications, "_send_webhook", lambda *a, **kw: (sent.append("webhook") or next(results)))
    now = datetime(2026, 11, 2, 10, tzinfo=UTC)

    first = daily_digest.run_due(db_session, now=now)
    assert first.status == "retry"
    assert first.delivered_channels == ["email"]
    assert daily_digest.run_due(db_session, now=now + timedelta(seconds=30)) is None
    db_session.expire_all()
    second = daily_digest.run_due(db_session, now=now + timedelta(minutes=2))

    assert first.digest_id == second.digest_id
    assert second.status == "sent"
    assert second.attempts == 2
    assert sent == ["email", "webhook", "webhook"]
    assert db_session.query(DigestRun).count() == 1


def test_digest_retry_is_bounded(db_session, monkeypatch):
    _config(db_session, host="smtp.example.test")
    monkeypatch.setattr(notifications, "_send_email", lambda *a: (False, "SMTP unavailable"))
    now = datetime(2026, 11, 2, 10, tzinfo=UTC)
    first = daily_digest.run_due(db_session, now=now)
    for attempt in range(1, 5):
        run = daily_digest.run_due(db_session, now=now + timedelta(hours=attempt * 2))
    assert run.digest_id == first.digest_id
    assert run.attempts == 5
    assert run.status == "dead"
    assert run.next_attempt_at is None
    assert daily_digest.run_due(db_session, now=now + timedelta(hours=9)) is None


def test_digest_transport_does_not_hold_sqlite_write_transaction(db_session, monkeypatch):
    _config(db_session, host="smtp.example.test")
    observed = []

    def send(*args):
        # Reading settings may start a SQLAlchemy transaction, but no pending
        # state has been flushed into SQLite during the external network call.
        connection = db_session.connection().connection.driver_connection
        observed.append(connection.in_transaction)
        return True, "ok"

    monkeypatch.setattr(notifications, "_send_email", send)
    run = daily_digest.run_due(db_session, now=datetime(2026, 11, 2, 10, tzinfo=UTC))
    assert run.status == "sent"
    assert observed == [False]


def test_digest_resumes_interrupted_processing_after_lease(db_session, monkeypatch):
    _config(db_session, host="smtp.example.test")
    now = datetime(2026, 11, 2, 10, tzinfo=UTC)
    run = DigestRun(
        digest_id="interrupted-digest", local_date="2026-11-01", timezone="UTC",
        status="processing", attempts=1, next_attempt_at=now + timedelta(minutes=10),
        summary={"local_date": "2026-11-01", "timezone": "UTC", "counts": {}, "total": 0},
    )
    db_session.add(run)
    db_session.commit()
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (True, "ok"))
    assert daily_digest.run_due(db_session, now=now + timedelta(minutes=5)) is None
    resumed = daily_digest.run_due(db_session, now=now + timedelta(minutes=11))
    assert resumed.digest_id == run.digest_id
    assert resumed.status == "sent"
    assert resumed.attempts == 2
