from __future__ import annotations

from dataclasses import replace

import pytest
from PIL import Image

from app.services import ocr, pipeline_readiness
from app.services.ollama_client import OllamaStatus
from app.settings import Settings


class _Client:
    status_result = OllamaStatus(True, "http://ollama", ["llama3.2:3b"])

    def __init__(self, *args, **kwargs):
        pass

    async def status(self):
        return self.status_result


@pytest.mark.asyncio
async def test_rules_only_requires_ocr_but_not_ollama(monkeypatch):
    config = Settings(classifier_mode="rules_only")
    monkeypatch.setattr(pipeline_readiness, "probe_tesseract", lambda *args, **kwargs: {"ok": True, "status": "ok"})
    checks = await pipeline_readiness.dependency_checks(config)
    assert checks == {
        "configuration": {"ok": True, "mode": "rules_only", "error_code": None},
        "ocr": {"ok": True, "status": "ok"},
    }


@pytest.mark.asyncio
async def test_text_llm_fails_when_model_is_missing(monkeypatch):
    config = Settings(classifier_mode="text_llm")
    monkeypatch.setattr(pipeline_readiness, "probe_tesseract", lambda *args, **kwargs: {"ok": True, "status": "ok"})
    _Client.status_result = replace(_Client.status_result, models=[])
    monkeypatch.setattr(pipeline_readiness, "OllamaClient", _Client)
    checks = await pipeline_readiness.dependency_checks(config)
    assert checks["text_model"]["ok"] is False
    assert checks["text_model"]["error_code"] == "model_missing"


def test_ocr_distinguishes_invalid_image(monkeypatch):
    monkeypatch.setattr(ocr, "probe_tesseract", lambda languages=None: {"ok": True})
    result = ocr.extract_tesseract(b"not an image")
    assert result.status == ocr.OcrStatus.IMAGE_DECODE_FAILED
    assert result.error_code == "invalid_image"


def test_ocr_reports_no_readable_text(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "probe_tesseract", lambda languages=None: {"ok": True})
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda *args, **kwargs: "")
    image = Image.new("RGB", (32, 32), "white")
    path = tmp_path / "blank.png"
    image.save(path)
    result = ocr.extract_tesseract(path.read_bytes())
    assert result.status == ocr.OcrStatus.NO_TEXT
    assert result.ok
