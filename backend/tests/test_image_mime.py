from __future__ import annotations

import io

import pytest
from PIL import Image

from app.db.models import Device, EvidenceBlob, Event


def _image_bytes(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buf, format=fmt)
    return buf.getvalue()


def test_validate_image_bytes_detects_actual_mime_type():
    from app.api.events import _validate_image_bytes

    assert _validate_image_bytes(_image_bytes("JPEG")) == "image/jpeg"
    assert _validate_image_bytes(_image_bytes("PNG")) == "image/png"


@pytest.mark.asyncio
async def test_screenshot_evidence_persists_png_mime(db_session, monkeypatch):
    from app.services import screenshot_ingest

    db_session.add(Device(device_id="dev1", hostname="kid-pc", paired=True))
    db_session.commit()

    monkeypatch.setattr(screenshot_ingest.settings, "classifier_tier", "text_only")
    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", lambda _: "self harm plan")

    async def fake_classify_text(**_kwargs):
        return {
            "risk_level": "high",
            "score": 80,
            "categories": ["self_harm"],
            "summary": "risk",
            "evidence": ["self harm"],
            "recommended_action": "alert_parent",
            "model": "fake",
            "rules_triggered": [],
            "confidence": 0.9,
            "false_positive_notes": "",
            "prompt_version": "test",
            "rules_version": None,
            "status": "ok",
        }

    monkeypatch.setattr(screenshot_ingest.classifier, "classify_text", fake_classify_text)

    result = await screenshot_ingest.ingest_screenshot(
        db_session,
        image_bytes=_image_bytes("PNG"),
        device_id="dev1",
        mime_type="image/png",
    )
    db_session.commit()

    event = db_session.get(Event, result["event_id"])
    blob = db_session.get(EvidenceBlob, event.screenshot_blob_id)
    assert blob.mime_type == "image/png"
