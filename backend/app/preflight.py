"""First-run dependency validation for installers and containers."""
from __future__ import annotations

from app.services.ollama_client import OllamaClient, OllamaError
from app.services.pipeline_readiness import dependency_checks
from app.settings import settings


async def run(*, pull_models: bool = False) -> tuple[int, dict]:
    checks = await dependency_checks()
    if pull_models:
        requested: list[tuple[str, str]] = []
        mode = settings.classifier_mode_resolved
        if mode in {"text_llm", "full"} and not checks.get("text_model", {}).get("model_present"):
            requested.append((settings.text_ollama_url_resolved, settings.text_model))
        if mode in {"vision", "full"} and not checks.get("vision_model", {}).get("model_present"):
            requested.append((settings.vision_ollama_url_resolved, settings.vision_model))
        pull_errors: list[dict[str, str]] = []
        for endpoint, model in requested:
            try:
                await OllamaClient(base_url=endpoint).pull(model)
            except OllamaError as exc:
                pull_errors.append({"model": model, "error_code": type(exc).__name__})
        checks = await dependency_checks()
        if pull_errors:
            checks["model_initialization"] = {
                "ok": False,
                "error_code": "model_pull_failed",
                "failures": pull_errors,
            }
    ok = all(bool(item.get("ok")) for item in checks.values())
    body = {"ok": ok, "mode": settings.classifier_mode_resolved, "checks": checks}
    if ok:
        return 0, body
    if not checks.get("configuration", {}).get("ok", True):
        return 2, body
    model_checks = [checks[name] for name in ("text_model", "vision_model") if name in checks]
    if any(item.get("error_code") in {"model_missing", "model_pull_failed"} for item in model_checks):
        return 4, body
    return 3, body
