"""Saved thresholds and current profile policy must control real delivery."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    ChildProfile,
    ConsentRecord,
    Device,
    Event,
    NotificationJob,
    RiskResult,
    Setting,
    User,
)
from app.services import consent, event_ingest, notifications, screenshot_ingest
from app.services.notification_status import delivery_status


def _config(db, floor="high", **extra):
    db.merge(Setting(key="notification_settings", value=json.dumps({
        "enabled": True, "host": "smtp.example.test", "immediate_min_severity": floor, **extra,
    })))
    db.commit()


def _profile(db, *, policy=None):
    profile = ChildProfile(profile_id="child-routing", display_name="Synthetic child", age_group="under_10",
                           alert_policy=policy or {})
    db.add(profile)
    db.add(Device(device_id="device-routing", hostname="synthetic-pc", paired=True,
                  profile_id=profile.profile_id))
    db.commit()
    return profile


def _alert(db, severity="high", category="scam", *, policy=None):
    _profile(db, policy=policy)
    db.add(Event(event_id="event-routing", device_id="device-routing", profile_id="child-routing",
                 source_type="system", timestamp=datetime.now(UTC)))
    db.flush()
    db.add(RiskResult(risk_id="risk-routing", event_id="event-routing", risk_level=severity,
                      categories=[category], score=75))
    db.flush()
    alert = Alert(alert_id="alert-routing", risk_id="risk-routing", device_id="device-routing",
                  profile_id="child-routing", severity=severity)
    db.add(alert)
    db.flush()
    return alert


@pytest.mark.parametrize("floor,severity,category,expected", [
    ("low", "low", "profanity", True),
    ("medium", "medium", "bullying", True),
    ("high", "medium", "bullying", False),
    ("critical", "high", "scam", False),
    ("critical", "critical", "scam", True),
    ("critical", "high", "grooming", True),
    ("low", "low", "custom_watch", True),
    ("invalid", "medium", "bullying", False),
])
def test_saved_threshold_controls_queue_and_preserves_protected_floor(
    db_session, floor, severity, category, expected
):
    _config(db_session, floor)
    alert = _alert(db_session, severity, category)
    job = notifications.enqueue(db_session, alert=alert, risk_summary="synthetic signal", immediate=True)
    assert (job is not None) is expected


@pytest.mark.parametrize("mode", ["monitor", "allow"])
def test_lower_threshold_never_overrides_quiet_profile_categories(db_session, mode):
    _config(db_session, "low")
    alert = _alert(db_session, "high", "scam", policy={"categories": {"scam": {"mode": mode}}})
    assert notifications.enqueue(db_session, alert=alert, risk_summary="synthetic") is None


def test_explicit_quiet_request_is_preserved(db_session):
    _config(db_session, "low")
    alert = _alert(db_session, "critical", "grooming")
    assert notifications.enqueue(db_session, alert=alert, risk_summary="synthetic", immediate=False) is None


@pytest.mark.parametrize("change", ["threshold", "profile", "disabled"])
def test_queue_rechecks_settings_before_external_delivery(db_session, monkeypatch, change):
    _config(db_session)
    alert = _alert(db_session)
    job = notifications.enqueue(db_session, alert=alert, risk_summary="synthetic", immediate=True)
    db_session.commit()
    if change == "threshold":
        _config(db_session, "critical")
    elif change == "profile":
        db_session.get(ChildProfile, "child-routing").alert_policy = {"categories": {"scam": {"mode": "monitor"}}}
        db_session.commit()
    else:
        _config(db_session, enabled=False)
    monkeypatch.setattr(notifications, "_send_email", lambda *args: pytest.fail("Suppressed job reached transport"))
    assert notifications.process_pending(db_session) == 1
    assert job.status == "skipped"
    assert job.next_attempt_at is None
    if change != "disabled":
        assert delivery_status(db_session)["recent_jobs"][0]["skip_reason"] == "current_policy"
        assert job.attempts == 0


def test_retry_rechecks_policy_without_resending_a_successful_channel(db_session, monkeypatch):
    _config(db_session, webhook_url="https://notify.example.test/hook")
    alert = _alert(db_session)
    job = notifications.enqueue(db_session, alert=alert, risk_summary="synthetic")
    db_session.commit()
    attempts = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (attempts.append("email") or (True, "ok")))
    monkeypatch.setattr(notifications, "_send_webhook", lambda *args, **kwargs: (attempts.append("webhook") or (False, "retry")))
    now = datetime.now(UTC)
    assert notifications.process_pending(db_session, now=now) == 1
    assert job.status == "retry"
    assert job.delivered_channels == ["email"]
    _config(db_session, "critical")
    assert notifications.process_pending(db_session, now=now + timedelta(minutes=2)) == 1
    assert attempts == ["email", "webhook"]
    assert job.status == "skipped"
    assert job.delivered_channels == ["email"]


def test_lowering_threshold_does_not_backfill_historical_alerts(db_session):
    _config(db_session, "high")
    alert = _alert(db_session, "low", "profanity")
    assert notifications.enqueue(db_session, alert=alert, risk_summary="synthetic") is None
    db_session.commit()
    _config(db_session, "low")
    assert notifications.process_pending(db_session) == 0
    assert db_session.query(NotificationJob).count() == 0


def test_screenshot_policy_reads_saved_notification_floor(db_session):
    _profile(db_session)
    _config(db_session, "low")
    assert screenshot_ingest._apply_policy(db_session, "child-routing", "low", ["profanity"]).notify
    _config(db_session, "critical")
    assert not screenshot_ingest._apply_policy(db_session, "child-routing", "high", ["scam"]).notify
    assert screenshot_ingest._apply_policy(db_session, "child-routing", "high", ["grooming"]).notify


@pytest.mark.asyncio
async def test_text_ingestion_queues_lower_severity_when_parent_selects_it(db_session, monkeypatch):
    _profile(db_session)
    _config(db_session, "low")

    async def classify(**kwargs):
        return {
            "risk_level": "low", "score": 20, "categories": ["profanity"],
            "summary": "Synthetic low finding", "evidence": [], "recommended_action": "review",
            "model": None, "rules_triggered": [], "confidence": 0.9, "false_positive_notes": "",
            "prompt_version": "test", "rules_version": "test",
        }

    monkeypatch.setattr(event_ingest.classifier, "classify_text", classify)
    result = await event_ingest.ingest_event(db_session, device_id="device-routing", payload={
        "source_type": "system", "redacted_text": "Synthetic text",
    })
    db_session.commit()
    assert result["alert_id"] is not None
    assert db_session.query(NotificationJob).filter_by(alert_id=result["alert_id"], status="queued").count() == 1


def test_synthetic_channel_test_remains_independent_of_alert_threshold(monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (sent.append(True) or (True, "ok")))
    assert notifications.run_test({"enabled": True, "host": "smtp.example.test", "immediate_min_severity": "critical"})[0]["ok"]
    assert sent == [True]


@pytest.mark.parametrize("change", ["disabled", "threshold", "profile", "consent"])
def test_policy_change_in_another_session_between_channels_stops_later_send(db_session, monkeypatch, change):
    _config(db_session, webhook_url="https://notify.example.test/hook")
    alert = _alert(db_session)
    parent = User(display_name="Parent", role="admin", password_hash="synthetic", recovery_hash="synthetic")
    db_session.add(parent)
    db_session.flush()
    db_session.add(ConsentRecord(
        consent_id="routing-consent", user_id=parent.id, notice_version=consent.NOTICE_VERSION,
        status="granted", choices={"child_notice_acknowledged": True, "notifications": True},
    ))
    db_session.commit()
    job = notifications.enqueue(db_session, alert=alert, risk_summary="synthetic")
    db_session.commit()
    sent = []

    def email(*args):
        sent.append("email")
        with Session(bind=db_session.get_bind()) as other:
            if change in {"disabled", "threshold"}:
                row = other.get(Setting, "notification_settings")
                config = json.loads(row.value)
                config.update({"enabled": False} if change == "disabled" else {"immediate_min_severity": "critical"})
                row.value = json.dumps(config)
            elif change == "profile":
                other.get(ChildProfile, "child-routing").alert_policy = {"categories": {"scam": {"mode": "monitor"}}}
            else:
                other.add(ConsentRecord(
                    consent_id="routing-consent-new", user_id=parent.id, notice_version=consent.NOTICE_VERSION,
                    status="granted", choices={"child_notice_acknowledged": True, "notifications": False},
                ))
            other.commit()
        return True, "ok"

    monkeypatch.setattr(notifications, "_send_email", email)
    monkeypatch.setattr(notifications, "_send_webhook", lambda *args, **kwargs: pytest.fail("Later channel used stale policy"))
    assert notifications.process_pending(db_session) == 1
    assert sent == ["email"]
    assert job.delivered_channels == ["email"]
    assert job.status == "sent"  # The first channel was accepted before the change.
