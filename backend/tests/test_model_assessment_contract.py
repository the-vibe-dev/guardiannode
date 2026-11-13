"""An invalid model response is incomplete review, never a clean screenshot."""
from __future__ import annotations

import json

import pytest

from app import settings as settings_mod
from app.api.dashboard import capture_status
from app.db.models import Alert, Base, Device, Event, RiskResult
from app.db.session import get_engine, get_sessionmaker
from app.services import (
    classifier,
    image_safety,
    pipeline_metrics,
    screenshot_async,
    screenshot_ingest,
)
from app.services.ocr import OcrResult, OcrStatus
from app.services.ollama_client import OllamaClient


def _assessment(*, vision=False):
    result = {
        "risk_level": "none", "score": 0, "categories": [], "summary": "Ordinary synthetic screen.",
        "recommended_action": "none", "confidence": 0.8, "false_positive_notes": "",
    }
    if vision:
        result.update(visible_text="", persons_visible=False, apparent_minor=False, visual_evidence=[])
    else:
        result["evidence"] = []
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["{}", "[]", "null", "0", '{"risk_level":"none"}', '{"risk_level":"none","score":"0","categories":[]}'])
async def test_incomplete_or_wrong_shaped_json_never_marks_model_success(monkeypatch, response):
    async def generate(self, **_kwargs):
        return response

    monkeypatch.setattr(OllamaClient, "generate", generate)
    text = await classifier.classify_text(redacted_text="ordinary synthetic words")
    vision = await image_safety.classify_image(image_bytes=b"synthetic", model="synthetic-vision")
    for result in (text, vision):
        assert result["model"] is None
        assert result["status"] == "unclassified_invalid_model_response"
    rules = await classifier.classify_text(redacted_text="don't tell your parents about this")
    assert rules["risk_level"] == "critical"
    assert rules["rules_triggered"]
    assert rules["status"] == "unclassified_invalid_model_response"


@pytest.mark.asyncio
async def test_complete_assessment_is_required_for_both_model_boundaries(monkeypatch):
    async def generate(self, **kwargs):
        return json.dumps(_assessment(vision=bool(kwargs.get("images"))))

    monkeypatch.setattr(OllamaClient, "generate", generate)
    text = await classifier.classify_text(redacted_text="ordinary words")
    vision = await image_safety.classify_image(image_bytes=b"synthetic", model="synthetic-vision")
    assert text["model"] is not None and text["status"] == "ok"
    assert vision["model"] == "synthetic-vision" and vision["status"] == "ok"


@pytest.mark.parametrize("tier,vision,text,ocr,status", [
    ("full", {}, {"model": "text"}, OcrResult(status=OcrStatus.OK, text="words"), "unclassified_vision_unavailable"),
    ("full", {"model": "vision"}, {}, OcrResult(status=OcrStatus.OK, text="words"), "unclassified_text_unavailable"),
    ("vision", {"status": "unclassified_invalid_model_response"}, {}, OcrResult(status=OcrStatus.NO_TEXT), "unclassified_invalid_vision_response"),
    ("full", {"model": "vision"}, {}, OcrResult(status=OcrStatus.NO_TEXT), "ok"),
    ("text_llm", {}, {}, OcrResult(status=OcrStatus.NO_TEXT), "no_text_to_review"),
    ("rules_only", {}, {}, OcrResult(status=OcrStatus.NO_TEXT), "ok"),
])
def test_completion_is_specific_to_required_modalities(tier, vision, text, ocr, status):
    assert screenshot_ingest._classifier_status(tier, ocr, vision, text) == status


def _configured_vision(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "classifier_mode", "vision")
    monkeypatch.setattr(screenshot_ingest, "settings", settings_mod.settings)
    monkeypatch.setattr(image_safety, "settings", settings_mod.settings)
    Base.metadata.create_all(get_engine())
    with get_sessionmaker()() as db:
        db.add(Device(device_id="model-device", hostname="synthetic", paired=True))
        db.commit()

    async def available():
        return True, ["synthetic-vision"]

    async def invalid(self, **_kwargs):
        return "{}"

    monkeypatch.setattr(screenshot_ingest, "_vision_available", available)
    monkeypatch.setattr(OllamaClient, "generate", invalid)


@pytest.mark.asyncio
async def test_invalid_nonrisk_capture_stays_encrypted_in_retry_queue(monkeypatch):
    _configured_vision(monkeypatch)
    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", lambda _image: OcrResult(status=OcrStatus.NO_TEXT))
    pipeline_metrics.reset_for_tests()
    token = screenshot_async.store_pending(b"synthetic-screen", {"device_id": "model-device"})
    try:
        with pytest.raises(screenshot_ingest.InvalidModelAssessmentError) as error:
            await screenshot_async._classify_token(token)
        screenshot_async._record_failure(token, error.value)
        assert (settings_mod.settings.data_dir / "pending" / f"{token}.enc").exists()
        assert screenshot_async._load_meta(token)["attempts"] == 1
        with get_sessionmaker()() as db:
            assert db.query(Event).count() == 0
            assert db.query(RiskResult).count() == 0
            status = capture_status(db, None)  # type: ignore[arg-type]
            assert status.devices[0].last_review_status == "not_reviewed"
            assert status.devices[0].pending_review_count == 1
            assert status.review_failures_5m == 1
    finally:
        pipeline_metrics.reset_for_tests()


@pytest.mark.asyncio
async def test_strong_rules_finding_is_preserved_immediately_with_degraded_model_status(monkeypatch):
    _configured_vision(monkeypatch)
    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", lambda _image: "don't tell your parents about this")
    with get_sessionmaker()() as db:
        result = await screenshot_ingest.ingest_screenshot(db, image_bytes=b"synthetic-screen", device_id="model-device")
        db.commit()
        assert result["risk_level"] == "critical"
        assert result["blob_stored"] is True
        assert result["vision_used"] is False
        risk = db.get(RiskResult, result["risk_id"])
        assert risk.classifier_status == "unclassified_invalid_vision_response"
        assert db.get(Alert, result["alert_id"]) is not None
        status = capture_status(db, None)  # type: ignore[arg-type]
        assert status.devices[0].last_review_status == "degraded"
        assert status.devices[0].review_model is None
