from __future__ import annotations

import pytest

from app import preflight


@pytest.mark.asyncio
async def test_preflight_exit_codes(monkeypatch):
    monkeypatch.setattr(preflight.settings, "classifier_mode", "rules_only")

    async def checks_ok():
        return {"configuration": {"ok": True}, "ocr": {"ok": True}}

    monkeypatch.setattr(preflight, "dependency_checks", checks_ok)
    code, body = await preflight.run()
    assert code == 0
    assert body["ok"] is True

    async def invalid_config():
        return {"configuration": {"ok": False, "error_code": "unsupported_classifier_mode"}}

    monkeypatch.setattr(preflight, "dependency_checks", invalid_config)
    code, _ = await preflight.run()
    assert code == 2

    async def missing_dependency():
        return {
            "configuration": {"ok": True},
            "ocr": {"ok": False, "error_code": "TesseractNotFoundError"},
        }

    monkeypatch.setattr(preflight, "dependency_checks", missing_dependency)
    code, _ = await preflight.run()
    assert code == 3

    monkeypatch.setattr(preflight.settings, "classifier_mode", "text_llm")

    async def missing_model():
        return {
            "configuration": {"ok": True},
            "ocr": {"ok": True},
            "text_model": {"ok": False, "model_present": False, "error_code": "model_missing"},
        }

    monkeypatch.setattr(preflight, "dependency_checks", missing_model)
    code, _ = await preflight.run()
    assert code == 4
