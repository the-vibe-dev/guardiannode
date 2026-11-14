"""Screenshot completion must retain model provenance and current authority."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app import settings as settings_mod
from app.api.dashboard import capture_status
from app.db.models import (
    AuditLog,
    Base,
    ChildProfile,
    ConsentRecord,
    Device,
    Event,
    EvidenceBlob,
    RiskResult,
    User,
)
from app.db.session import get_engine, get_sessionmaker
from app.services import consent, pipeline_metrics, screenshot_async, screenshot_ingest


def _database(monkeypatch, *, mode="full"):
    monkeypatch.setattr(settings_mod.settings, "classifier_mode", mode)
    monkeypatch.setattr(screenshot_ingest, "settings", settings_mod.settings)
    Base.metadata.create_all(get_engine())
    with get_sessionmaker()() as db:
        db.add(Device(device_id="capture-device", hostname="synthetic", paired=True))
        db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("text_valid", [True, False])
async def test_full_review_preserves_text_provenance_when_vision_ocr_raises_rules_floor(monkeypatch, text_valid):
    _database(monkeypatch)
    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", lambda _: "ordinary synthetic words")

    async def available():
        return True, ["synthetic-vision"]

    async def vision(**_kwargs):
        return {
            "model": "synthetic-vision", "status": "ok", "risk_level": "none", "score": 0,
            "visible_text": "don't tell your parents about this", "categories": [], "confidence": 0.8,
        }

    async def text(**_kwargs):
        return {
            "model": "synthetic-text" if text_valid else None,
            "status": "ok" if text_valid else "unclassified_invalid_model_response",
            "prompt_version": "synthetic-prompt", "risk_level": "none", "score": 0,
            "categories": [], "evidence": [], "confidence": 0.8 if text_valid else 0,
        }

    monkeypatch.setattr(screenshot_ingest, "_vision_available", available)
    monkeypatch.setattr(screenshot_ingest.image_safety, "classify_image", vision)
    monkeypatch.setattr(screenshot_ingest.classifier, "classify_text", text)
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(
            db, image_bytes=b"synthetic screen", device_id="capture-device",
        )
        db.commit()
        risk = db.get(RiskResult, result["risk_id"])
        event = db.get(Event, result["event_id"])
        expected = "ok" if text_valid else "unclassified_invalid_text_response"
        assert risk.risk_level == "critical"
        assert result["blob_stored"] is True
        assert risk.classifier_status == expected
        assert event.event_metadata["text_model"] == ("synthetic-text" if text_valid else None)
        assert event.event_metadata["text_status"] == ("ok" if text_valid else "unclassified_invalid_model_response")
        assert capture_status(db, None).devices[0].last_review_status == ("ai_reviewed" if text_valid else "degraded")


@pytest.mark.asyncio
async def test_inflight_capture_is_discarded_after_active_consent_generation_changes(monkeypatch):
    _database(monkeypatch, mode="rules_only")
    pipeline_metrics.reset_for_tests()
    choices = {"screenshots": True, "retention": True, "apps_and_urls": True, "child_notice_acknowledged": True}
    with get_sessionmaker()() as db:
        user = User(display_name="Synthetic parent", password_hash="synthetic", recovery_hash="synthetic")
        db.add(user)
        db.flush()
        db.add(ConsentRecord(
            consent_id="original-generation", user_id=user.id, notice_version=consent.NOTICE_VERSION,
            status="granted", choices=choices,
        ))
        db.commit()
    token = screenshot_async.store_pending(b"synthetic screen", {
        "device_id": "capture-device", "policy_generation": "original-generation",
    })

    def change_generation(_image):
        with get_sessionmaker()() as other:
            user = other.query(User).one()
            other.add(ConsentRecord(
                consent_id="new-generation", user_id=user.id, notice_version=consent.NOTICE_VERSION,
                status="granted", choices=choices, created_at=datetime.now(UTC) + timedelta(seconds=1),
            ))
            other.commit()
        return "don't tell your parents about this"

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", change_generation)
    await screenshot_async._classify_token(token)
    with get_sessionmaker()() as db:
        assert consent.processing_allowed(db, screenshots=True) is True
        assert db.query(Event).count() == 0
        assert db.query(RiskResult).count() == 0
        assert db.query(EvidenceBlob).count() == 0
    assert not list(settings_mod.settings.evidence_dir.rglob("*.enc"))
    assert screenshot_async._load_meta(token) is None
    assert not (settings_mod.settings.data_dir / "pending" / f"{token}.enc").exists()
    snapshot = pipeline_metrics.snapshot(window_seconds=300)
    assert snapshot["discarded_frames_in_window"] == 1
    assert snapshot["failed_frames_in_window"] == 0
    assert snapshot["throughput"]["frames_in_window"] == 0
    assert snapshot["last_classified_at"] is None
    pipeline_metrics.reset_for_tests()


@pytest.mark.asyncio
async def test_inflight_capture_is_not_attached_to_a_stale_child_assignment(monkeypatch):
    _database(monkeypatch, mode="rules_only")
    with get_sessionmaker()() as db:
        db.add_all([
            ChildProfile(profile_id="child-a", display_name="Child A", age_group="10_13"),
            ChildProfile(profile_id="child-b", display_name="Child B", age_group="under_10"),
        ])
        db.flush()
        db.get(Device, "capture-device").profile_id = "child-a"
        db.commit()

    def reassign(_image):
        with get_sessionmaker()() as other:
            other.get(Device, "capture-device").profile_id = "child-b"
            other.commit()
        return "don't tell your parents about this"

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", reassign)
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(db, image_bytes=b"synthetic screen", device_id="capture-device")
        db.commit()
        assert result["status"] == "discarded"
        assert result["discard_reason"] == "profile_changed"
        assert db.query(Event).count() == 0
        assert db.query(EvidenceBlob).count() == 0


@pytest.mark.asyncio
async def test_final_authority_check_and_persistence_hold_one_sqlite_write_transaction(monkeypatch):
    _database(monkeypatch, mode="rules_only")
    path = get_engine().url.database
    checks = 0
    original = screenshot_ingest._monitoring_active

    def extract_without_write_lock(_image):
        # Expensive OCR/model work must not block parent privacy changes.
        with sqlite3.connect(path) as concurrent_parent:
            concurrent_parent.execute("PRAGMA busy_timeout=0")
            concurrent_parent.execute("BEGIN IMMEDIATE")
            concurrent_parent.rollback()
        return "don't tell your parents about this"

    def final_check_is_serialized(db, device):
        nonlocal checks
        checks += 1
        allowed = original(db, device)
        if checks == 2:
            # This independent connection stands in for a concurrent parent
            # withdrawal/reassignment. It cannot commit after our final check
            # but before the new evidence chain is committed.
            with sqlite3.connect(path) as concurrent_parent:
                concurrent_parent.execute("PRAGMA busy_timeout=0")
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    concurrent_parent.execute("BEGIN IMMEDIATE")
        return allowed

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", extract_without_write_lock)
    monkeypatch.setattr(screenshot_ingest, "_monitoring_active", final_check_is_serialized)
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(
            db, image_bytes=b"synthetic screen", device_id="capture-device",
            profile_id="stale-device-profile",
        )
        db.commit()
        assert result["blob_stored"] is True
        assert db.query(AuditLog).filter(AuditLog.action == "device.profile_mismatch").count() == 1
    assert checks == 2
    with sqlite3.connect(path) as concurrent_parent:
        concurrent_parent.execute("PRAGMA busy_timeout=0")
        concurrent_parent.execute("BEGIN IMMEDIATE")
        concurrent_parent.rollback()
