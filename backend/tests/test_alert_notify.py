"""upsert_alert(notify=True) must actually dispatch a notification.

Regression guard: notifications.dispatch was previously never called from the
alert path, so email/webhook alerts never fired.
"""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from app.db.models import Device, Event, NotificationJob, NotificationLog, RiskResult, Setting
from app.services.alert_dedup import upsert_alert


def _seed(db, risk_id="r1", event_id="e1"):
    db.merge(Device(device_id="dev1", hostname="kid-pc", paired=True))
    db.flush()
    db.add(Event(event_id=event_id, device_id="dev1", source_type="screenshot",
                 timestamp=datetime.now(UTC)))
    db.flush()
    db.add(RiskResult(risk_id=risk_id, event_id=event_id, risk_level="high", score=75,
                      categories=["grooming"], summary="bad", evidence=[],
                      recommended_action="alert_parent", confidence=0.9))
    db.flush()


def test_notify_true_records_notification(db_session):
    _seed(db_session)
    aid, created = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="high", categories=["grooming"], source="screenshot",
        notify=True, risk_summary="bad",
    )
    assert created
    db_session.flush()
    logs = db_session.query(NotificationLog).filter(NotificationLog.alert_id == aid).all()
    assert any(log.channel == "dashboard" for log in logs)
    jobs = db_session.query(NotificationJob).filter(NotificationJob.alert_id == aid).all()
    assert len(jobs) == 1
    assert jobs[0].status == "queued"


def test_notify_false_does_not_dispatch(db_session):
    _seed(db_session)
    aid, _ = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="medium", categories=["profanity"], source="screenshot",
        notify=False,
    )
    assert db_session.query(NotificationLog).filter(NotificationLog.alert_id == aid).count() == 0
    assert db_session.query(NotificationJob).filter(NotificationJob.alert_id == aid).count() == 0


def test_notify_job_delivers_external_channels_after_commit(db_session, monkeypatch):
    from app.services import encryption, notifications

    sent: list[str] = []
    monkeypatch.setattr(
        notifications,
        "_send_email",
        lambda cfg, subj, body: (sent.append("email") or (True, "ok")),
    )
    monkeypatch.setattr(
        notifications,
        "_send_webhook",
        lambda url, payload, **_kwargs: (sent.append("webhook") or (True, "ok")),
    )
    cfg = {
        "enabled": True,
        "host": "smtp.test.invalid",
        "webhook_url": "http://localhost:1/notify",
        "webhook_allow_private": True,
        "password_enc": base64.b64encode(encryption.encrypt_text("s3cr3t")).decode("ascii"),
    }
    db_session.add(Setting(key="notification_settings", value=json.dumps(cfg)))
    _seed(db_session)
    aid, created = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="high", categories=["grooming"], source="screenshot",
        notify=True, risk_summary="bad",
    )
    assert created
    db_session.commit()
    assert sent == []
    assert db_session.query(NotificationJob).filter_by(alert_id=aid, status="queued").count() == 1
    assert {row.channel for row in db_session.query(NotificationLog).filter_by(alert_id=aid).all()} == {
        "dashboard"
    }

    assert notifications.process_pending(db_session) == 1

    assert sent == ["email", "webhook"]
    assert db_session.query(NotificationJob).filter_by(alert_id=aid, status="sent").count() == 1
    persisted = db_session.query(NotificationLog).filter_by(alert_id=aid).all()
    assert {row.channel for row in persisted} == {"dashboard", "email", "webhook"}
