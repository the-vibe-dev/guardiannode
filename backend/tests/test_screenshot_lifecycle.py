"""Queued capture work must respect current parent choices and stay responsive."""
from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app import settings as settings_mod
from app.db.models import Base, ConsentRecord, Device, Event, EvidenceBlob, User
from app.db.session import get_engine, get_sessionmaker
from app.services import consent, screenshot_async, screenshot_ingest


def _database(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "classifier_mode", "rules_only")
    monkeypatch.setattr(screenshot_ingest, "settings", settings_mod.settings)
    Base.metadata.create_all(get_engine())
    with get_sessionmaker()() as db:
        db.add(Device(device_id="capture-device", hostname="synthetic-pc", paired=True))
        db.commit()


@pytest.mark.asyncio
async def test_cpu_ocr_runs_outside_asgi_event_loop(monkeypatch):
    _database(monkeypatch)
    observed = []

    def extract(_image):
        observed.append(threading.get_ident())
        return "ordinary synthetic chat"

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", extract)
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(
            db, image_bytes=b"synthetic frame", device_id="capture-device",
        )
        db.commit()
    assert result["event_id"]
    assert len(observed) == 1
    assert observed[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_revocation_during_ocr_discards_result_before_persistence(monkeypatch):
    _database(monkeypatch)

    def revoke_while_running(_image):
        with get_sessionmaker()() as other:
            other.get(Device, "capture-device").paired = False
            other.commit()
        return "free robux click here"

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", revoke_while_running)
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(
            db, image_bytes=b"synthetic frame", device_id="capture-device",
        )
        db.commit()
        assert result["status"] == "discarded"
        assert db.query(Event).count() == 0
        assert db.query(EvidenceBlob).count() == 0
    assert not list(settings_mod.settings.evidence_dir.rglob("*.enc"))


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["revoked", "paused"])
async def test_queued_capture_rechecks_current_device_state(monkeypatch, state):
    _database(monkeypatch)
    token = screenshot_async.store_pending(b"synthetic frame", {"device_id": "capture-device"})
    with get_sessionmaker()() as db:
        device = db.get(Device, "capture-device")
        if state == "revoked":
            device.paired = False
        else:
            device.paused_until = datetime.now(UTC) + timedelta(minutes=10)
        db.commit()

    async def unexpected_classification(*args, **kwargs):
        raise AssertionError("disabled capture must not reach classifier")

    monkeypatch.setattr(screenshot_ingest, "ingest_screenshot", unexpected_classification)
    await screenshot_async._classify_token(token)
    assert not (settings_mod.settings.data_dir / "pending" / f"{token}.enc").exists()
    assert not (settings_mod.settings.data_dir / "pending" / f"{token}.json").exists()


@pytest.mark.asyncio
async def test_screenshot_context_is_omitted_when_parent_opts_out(monkeypatch):
    _database(monkeypatch)
    observed = []
    original_start = screenshot_ingest.pipeline_metrics.start

    def capture_start(**kwargs):
        observed.append(kwargs)
        return original_start(**kwargs)

    monkeypatch.setattr(screenshot_ingest.pipeline_metrics, "start", capture_start)
    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", lambda _image: "ordinary chat")
    with get_sessionmaker()() as db:
        user = User(display_name="Synthetic parent", password_hash="synthetic", recovery_hash="synthetic")
        db.add(user)
        db.flush()
        db.add(ConsentRecord(
            consent_id="consent-context-test", user_id=user.id, notice_version=consent.NOTICE_VERSION,
            status="granted", choices={
                "screenshots": True, "retention": True, "apps_and_urls": False,
                "notifications": True, "child_notice_acknowledged": True,
            },
        ))
        db.commit()
        result = await screenshot_ingest.ingest_screenshot(
            db, image_bytes=b"synthetic frame", device_id="capture-device",
            app_name="private.exe", window_title="private title", url="https://private.example.test",
        )
        db.commit()
        event = db.get(Event, result["event_id"])
        assert event.app_name is event.window_title is event.url is None
    assert observed[0]["app_name"] is observed[0]["window_title"] is None
