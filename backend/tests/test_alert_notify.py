"""upsert_alert(notify=True) must actually dispatch a notification.

Regression guard: notifications.dispatch was previously never called from the
alert path, so email/webhook alerts never fired.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Event, NotificationLog, RiskResult
from app.services.alert_dedup import upsert_alert


def _seed(db, risk_id="r1", event_id="e1"):
    db.add(Event(event_id=event_id, device_id="dev1", source_type="screenshot",
                 timestamp=datetime.now(timezone.utc)))
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
    # dispatch always records the dashboard channel; that's proof it ran.
    assert any(l.channel == "dashboard" for l in logs)


def test_notify_false_does_not_dispatch(db_session):
    _seed(db_session)
    aid, _ = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="medium", categories=["profanity"], source="screenshot",
        notify=False,
    )
    assert db_session.query(NotificationLog).filter(NotificationLog.alert_id == aid).count() == 0
