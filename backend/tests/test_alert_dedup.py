"""Repeated identical findings fold into one alert instead of flooding the feed."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Alert, Event, RiskResult
from app.services.alert_dedup import upsert_alert


def _add_risk(db, risk_id: str, event_id: str) -> None:
    db.add(Event(
        event_id=event_id, device_id="dev1", source_type="screenshot",
        timestamp=datetime.now(timezone.utc),
    ))
    db.add(RiskResult(
        risk_id=risk_id, event_id=event_id, risk_level="critical", score=95,
        categories=["self_harm", "sexual_content"], summary="note", evidence=[],
        recommended_action="emergency_review", confidence=0.9,
    ))


def test_identical_findings_fold_into_one_alert(db_session):
    _add_risk(db_session, "r1", "e1")
    _add_risk(db_session, "r2", "e2")
    db_session.flush()

    a1, created1 = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="critical", categories=["self_harm", "sexual_content"],
        source="screenshot",
    )
    a2, created2 = upsert_alert(
        db_session, risk_id="r2", device_id="dev1", profile_id=None,
        severity="critical", categories=["sexual_content", "self_harm"],
        source="screenshot",
    )
    assert created1 is True
    assert created2 is False
    assert a1 == a2

    alert = db_session.get(Alert, a1)
    assert alert.repeat_count == 2
    assert alert.last_seen_at is not None
    assert alert.risk_id == "r2", "alert must point at the newest evidence"
    assert db_session.query(Alert).count() == 1


def test_different_severity_creates_new_alert(db_session):
    _add_risk(db_session, "r1", "e1")
    _add_risk(db_session, "r2", "e2")
    db_session.flush()

    a1, _ = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="high", categories=["self_harm"], source="screenshot",
    )
    a2, created = upsert_alert(
        db_session, risk_id="r2", device_id="dev1", profile_id=None,
        severity="critical", categories=["self_harm"], source="screenshot",
    )
    assert created is True
    assert a1 != a2, "an escalation must surface as its own alert"


def test_reviewed_alert_does_not_absorb_new_findings(db_session):
    _add_risk(db_session, "r1", "e1")
    _add_risk(db_session, "r2", "e2")
    db_session.flush()

    a1, _ = upsert_alert(
        db_session, risk_id="r1", device_id="dev1", profile_id=None,
        severity="critical", categories=["self_harm"], source="screenshot",
    )
    db_session.get(Alert, a1).status = "reviewed"
    db_session.flush()

    a2, created = upsert_alert(
        db_session, risk_id="r2", device_id="dev1", profile_id=None,
        severity="critical", categories=["self_harm"], source="screenshot",
    )
    assert created is True
    assert a1 != a2, "a reviewed alert is closed; recurrence needs fresh attention"
