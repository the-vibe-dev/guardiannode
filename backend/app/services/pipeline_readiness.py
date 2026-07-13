"""Mode-aware dependency checks shared by readiness and preflight."""
from __future__ import annotations

from app import settings as settings_mod
from app.services.ocr import probe_tesseract
from app.services.ollama_client import OllamaClient

VALID_MODES = {"rules_only", "text_llm", "vision", "full"}


async def dependency_checks(config=None) -> dict[str, dict]:
    config = config or settings_mod.settings
    mode = config.classifier_mode_resolved
    checks: dict[str, dict] = {
        "configuration": {
            "ok": mode in VALID_MODES,
            "mode": mode,
            "error_code": None if mode in VALID_MODES else "unsupported_classifier_mode",
        },
        "ocr": probe_tesseract(config.ocr_language_list, enabled=config.tesseract_enabled),
    }
    if mode in {"text_llm", "full"}:
        status = await OllamaClient(base_url=config.text_ollama_url_resolved).status()
        checks["text_model"] = {
            "ok": status.available and config.text_model in status.models,
            "endpoint_available": status.available,
            "model": config.text_model,
            "model_present": config.text_model in status.models,
            "error_code": None if status.available else "ollama_unavailable",
        }
        if status.available and config.text_model not in status.models:
            checks["text_model"]["error_code"] = "model_missing"
    if mode in {"vision", "full"}:
        status = await OllamaClient(base_url=config.vision_ollama_url_resolved).status()
        checks["vision_model"] = {
            "ok": status.available and config.vision_model in status.models,
            "endpoint_available": status.available,
            "model": config.vision_model,
            "model_present": config.vision_model in status.models,
            "error_code": None if status.available else "ollama_unavailable",
        }
        if status.available and config.vision_model not in status.models:
            checks["vision_model"]["error_code"] = "model_missing"
    return checks
