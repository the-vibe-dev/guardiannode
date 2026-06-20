"""Wipe/retention cascade behavior: no orphaned rows or evidence files."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app import settings as settings_mod
from app.db.models import Alert, Device, Event, EvidenceBlob, RiskResult
from app.services import purge, retention


def _old(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _mk_chain(s, tmp_path, *, suffix: str, severity: str, age_days: int, with_blob=True):
    """Create a full event → risk → alert → blob chain."""
    s.merge(Device(device_id="d1", hostname="kid-pc", paired=True))
    event_id = f"e-{suffix}"
    risk_id = f"r-{suffix}"
    blob_id = f"b-{suffix}" if with_blob else None
    blob_path = None
    s.flush()
    if with_blob:
        blob_path = settings_mod.settings.evidence_dir / blob_id[:2] / f"{blob_id}.enc"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"ciphertext")
        s.add(EvidenceBlob(
            blob_id=blob_id, kind="screenshot", encrypted_path=str(blob_path),
            size_bytes=10, event_id=event_id, created_at=_old(age_days),
        ))
    s.add(Event(
        event_id=event_id, device_id="d1", source_type="image",
        timestamp=_old(age_days), screenshot_blob_id=blob_id,
    ))
    s.flush()
    s.add(RiskResult(
        risk_id=risk_id, event_id=event_id, risk_level=severity, score=50,
        created_at=_old(age_days),
    ))
    s.flush()
    s.add(Alert(
        alert_id=f"a-{suffix}", risk_id=risk_id, severity=severity,
        created_at=_old(age_days),
    ))
    s.commit()
    return event_id, risk_id, blob_id, blob_path


def test_delete_events_cascades_risk_alert_blob(db_session, tmp_path):
    s = db_session
    event_id, risk_id, blob_id, blob_path = _mk_chain(
        s, tmp_path, suffix="x", severity="high", age_days=0)

    counts = purge.delete_events(s, [event_id])
    s.commit()

    assert counts == {"events": 1, "risk_results": 1, "alerts": 1, "blobs": 1}
    assert s.get(Event, event_id) is None
    assert s.get(RiskResult, risk_id) is None
    assert s.query(Alert).filter_by(risk_id=risk_id).first() is None
    assert s.get(EvidenceBlob, blob_id) is None
    assert not blob_path.exists()


def test_wipe_old_events_leaves_no_orphans(db_session, tmp_path):
    """The storage-wipe path (older_than_days) must clear the full chain."""
    s = db_session
    _mk_chain(s, tmp_path, suffix="old", severity="medium", age_days=40)
    keep_ids = _mk_chain(s, tmp_path, suffix="new", severity="medium", age_days=1)

    cutoff = datetime.now(UTC) - timedelta(days=30)
    old_ids = [r[0] for r in s.query(Event.event_id).filter(Event.timestamp < cutoff).all()]
    purge.delete_events(s, old_ids)
    s.commit()

    assert s.query(Event).count() == 1
    assert s.query(RiskResult).count() == 1
    assert s.query(Alert).count() == 1
    assert s.query(EvidenceBlob).count() == 1
    assert keep_ids[3].exists()


def test_retention_cleanup_no_orphans_and_keeps_high_severity(db_session, tmp_path):
    s = db_session
    # Low severity, 10 days old → gone (low retention default 1 day).
    _, _, _, low_blob = _mk_chain(s, tmp_path, suffix="low", severity="low", age_days=10)
    # High severity, 10 days old → kept (high retention 90 days).
    _, _, _, high_blob = _mk_chain(s, tmp_path, suffix="high", severity="high", age_days=10)
    # Critical, 200 days old → gone.
    _, _, _, crit_blob = _mk_chain(s, tmp_path, suffix="crit", severity="critical", age_days=200)

    retention.run_cleanup(s, retention.DEFAULT_RETENTION_DAYS)

    remaining_events = {e.event_id for e in s.query(Event).all()}
    assert remaining_events == {"e-high"}
    remaining_risks = {r.risk_id for r in s.query(RiskResult).all()}
    assert remaining_risks == {"r-high"}
    remaining_alerts = {a.alert_id for a in s.query(Alert).all()}
    assert remaining_alerts == {"a-high"}
    # No orphaned files left behind.
    assert not low_blob.exists()
    assert not crit_blob.exists()
    assert high_blob.exists()


def test_flagged_screenshot_blob_expires_before_alert_metadata(db_session, tmp_path):
    """screenshots_flagged window drops the image but keeps alert context."""
    s = db_session
    event_id, risk_id, blob_id, blob_path = _mk_chain(
        s, tmp_path, suffix="h", severity="high", age_days=40)  # > 30d blob window, < 90d alert

    retention.run_cleanup(s, retention.DEFAULT_RETENTION_DAYS)

    assert s.get(Event, event_id) is not None
    assert s.get(RiskResult, risk_id) is not None
    assert s.query(Alert).filter_by(risk_id=risk_id).first() is not None
    assert s.get(EvidenceBlob, blob_id) is None
    assert not blob_path.exists()
    assert s.get(Event, event_id).screenshot_blob_id is None


def test_orphaned_blob_sweep(db_session, tmp_path):
    s = db_session
    blob_path = settings_mod.settings.evidence_dir / "b-" / "b-orphan.enc"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"x")
    s.add(EvidenceBlob(
        blob_id="b-orphan", kind="screenshot", encrypted_path=str(blob_path),
        size_bytes=1, event_id="event-that-does-not-exist",
    ))
    s.commit()

    n = purge.delete_orphaned_blob_files(s)
    s.commit()
    assert n == 1
    assert s.get(EvidenceBlob, "b-orphan") is None
    assert not blob_path.exists()


def test_delete_blob_refuses_path_outside_evidence_root(db_session, tmp_path):
    s = db_session
    outside_path = tmp_path / "outside.enc"
    outside_path.write_bytes(b"do-not-touch")
    s.add(Device(device_id="d1", hostname="kid-pc", paired=True))
    s.flush()
    s.add(Event(
        event_id="e-outside", device_id="d1", source_type="image",
        timestamp=_old(0), screenshot_blob_id="b-outside",
    ))
    s.flush()
    s.add(EvidenceBlob(
        blob_id="b-outside", kind="screenshot", encrypted_path=str(outside_path),
        size_bytes=12, event_id="e-outside",
    ))
    s.commit()

    blob = s.get(EvidenceBlob, "b-outside")
    assert blob is not None
    purge.delete_blob(s, blob)
    s.commit()

    assert s.get(EvidenceBlob, "b-outside") is None
    assert outside_path.exists()


def test_wipe_low_severity_removes_chain(db_session, tmp_path):
    """Wiping low-severity records removes events + risk results, not just alerts."""
    s = db_session
    _mk_chain(s, tmp_path, suffix="lw", severity="low", age_days=0)
    _mk_chain(s, tmp_path, suffix="hi", severity="high", age_days=0)

    low_event_ids = [
        r[0] for r in s.query(RiskResult.event_id)
        .filter(RiskResult.risk_level.in_(["low", "none"])).all()
    ]
    purge.delete_events(s, low_event_ids)
    s.commit()

    assert {e.event_id for e in s.query(Event).all()} == {"e-hi"}
    assert {r.risk_id for r in s.query(RiskResult).all()} == {"r-hi"}
    assert {a.alert_id for a in s.query(Alert).all()} == {"a-hi"}
