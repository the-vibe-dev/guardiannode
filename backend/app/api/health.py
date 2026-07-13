"""Health endpoint — no auth, useful for installer self-tests + dashboard live status."""
from __future__ import annotations

import shutil
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.api.deps import current_user
from app.db.models import User
from app.services import pipeline_metrics
from app.services.ollama_client import OllamaClient
from app.settings import settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "service": "guardiannode-backend",
    }


@router.get("/health/live")
def liveness() -> dict:
    """Process liveness only; does not claim the safety pipeline is ready."""
    return health()


def _required_workers() -> set[str]:
    required = {"screenshot"}
    if settings.retention_cleanup_enabled:
        required.add("retention")
    if settings.device_offline_alert_enabled:
        required.add("offline")
    if settings.notification_worker_enabled:
        required.add("notifications")
    if settings.database_backup_enabled:
        required.add("backup")
    return required


@router.get("/health/ready")
async def readiness():
    """Fail closed unless storage, schema, workers, and active pipeline are ready."""
    from app.db.migrations import schema_revisions
    from app.db.session import get_engine
    from app.services import encryption, worker_supervisor

    checks: dict[str, dict] = {}
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    try:
        current, head = schema_revisions(engine)
        checks["schema"] = {"ok": current == head, "revision": current, "head": head}
    except Exception as exc:
        checks["schema"] = {"ok": False, "error": type(exc).__name__}

    try:
        checks["encryption"] = {"ok": encryption.current_key_version() >= 1}
    except Exception as exc:
        checks["encryption"] = {"ok": False, "error": type(exc).__name__}

    try:
        free = shutil.disk_usage(settings.data_dir).free
        checks["storage"] = {
            "ok": free >= settings.readiness_min_free_bytes,
            "free_bytes": free,
            "minimum_free_bytes": settings.readiness_min_free_bytes,
        }
    except Exception as exc:
        checks["storage"] = {"ok": False, "error": type(exc).__name__}

    workers_ok, workers = worker_supervisor.readiness(_required_workers())
    checks["workers"] = {"ok": workers_ok, "items": workers}
    from app.services.pipeline_readiness import dependency_checks

    pipeline = await dependency_checks(settings)
    checks["pipeline"] = {
        "ok": all(bool(item.get("ok")) for item in pipeline.values()),
        "mode": settings.classifier_mode_resolved,
        "items": pipeline,
    }
    ready = all(bool(item.get("ok")) for item in checks.values())
    body = {"status": "ready" if ready else "not_ready", "version": __version__, "checks": checks}
    return JSONResponse(body, status_code=200 if ready else 503)


class RuntimeSettingsResponse(BaseModel):
    version: str
    bind: dict[str, str | int]
    security: dict[str, str | bool | list[str]]
    classifier: dict[str, str | int | bool | None]
    ollama: dict[str, str | int]
    retention: dict[str, int | bool]
    device_offline: dict[str, int | bool]
    database: dict[str, str]


def _database_driver() -> str:
    parsed = urlparse(settings.db_url_resolved)
    return parsed.scheme or "unknown"


def _security_warnings() -> list[str]:
    warnings: list[str] = []
    if settings.binds_beyond_loopback():
        warnings.append(
            "Backend is listening beyond loopback. Keep GuardianNode on a trusted LAN/VPN/TLS "
            "path and do not expose it directly to the public internet."
        )
    if settings.cors_allow_origin:
        warnings.append("CORS is enabled for a configured origin; keep that origin parent-controlled.")
    if settings.allowed_hosts.strip() == "*":
        warnings.append("Wildcard Host headers are enabled for development mode only.")
    return warnings


@router.get("/health/runtime-settings", response_model=RuntimeSettingsResponse)
def runtime_settings(_: User = Depends(current_user)) -> RuntimeSettingsResponse:
    """Parent-only diagnostic view of effective non-secret runtime settings."""
    return RuntimeSettingsResponse(
        version=__version__,
        bind={"host": settings.bind_host, "port": settings.bind_port},
        security={
            "allowed_hosts": settings.effective_allowed_hosts(),
            "cors_allow_origin_configured": settings.cors_allow_origin is not None,
            "dev_mode": settings.dev_mode,
            "https_only_cookies": settings.https_only_cookies,
            "mdns_enabled": settings.mdns_enabled,
            "warnings": _security_warnings(),
        },
        classifier={
            "tier": settings.classifier_tier,
            "mode": settings.classifier_mode_resolved,
            "text_model": settings.text_model,
            "vision_model": settings.vision_model,
            "classifier_timeout_seconds": settings.classifier_timeout_seconds,
            "vision_num_ctx": settings.vision_num_ctx,
            "vision_max_image_edge": settings.vision_max_image_edge,
            "tesseract_enabled": settings.tesseract_enabled,
            "ocr_languages": ",".join(settings.ocr_language_list),
            "rules_version": settings.rules_version,
        },
        ollama={
            "base_url": settings.ollama_url,
            "text_url": settings.text_ollama_url_resolved,
            "vision_url": settings.vision_ollama_url_resolved,
            "status_timeout_seconds": settings.ollama_status_timeout_seconds,
            "pull_timeout_seconds": settings.ollama_pull_timeout_seconds,
        },
        retention={
            "cleanup_enabled": settings.retention_cleanup_enabled,
            "cleanup_interval_seconds": settings.retention_cleanup_interval_seconds,
        },
        device_offline={
            "alert_enabled": settings.device_offline_alert_enabled,
            "after_seconds": settings.device_offline_after_seconds,
            "check_interval_seconds": settings.device_offline_check_interval_seconds,
        },
        database={"driver": _database_driver()},
    )


@router.get("/health/pipeline")
async def pipeline_health(_: User = Depends(current_user)) -> dict:
    """Detailed pipeline status — what's processing right now + recent throughput.

    Polled by the parent dashboard to surface "is the system actively working?"
    """
    snap = pipeline_metrics.snapshot(window_seconds=300)

    # Per-role Ollama probes (may be different endpoints if vision/text are split)
    vision_url = settings.vision_ollama_url_resolved
    text_url = settings.text_ollama_url_resolved
    vision_client = OllamaClient(base_url=vision_url, timeout=3.0)
    if text_url != vision_url:
        text_client = OllamaClient(base_url=text_url, timeout=3.0)
        vision_status = await vision_client.status()
        text_status = await text_client.status()
    else:
        vision_status = await vision_client.status()
        text_status = vision_status  # same instance, only probe once

    text_present = settings.text_model in text_status.models if text_status.available else False
    vision_present = settings.vision_model in vision_status.models if vision_status.available else False

    # Tesseract availability (text_only tier + fallback OCR path).
    tesseract_available = False
    try:
        import pytesseract  # type: ignore
        tesseract_available = bool(pytesseract.get_tesseract_version())
    except Exception:
        tesseract_available = False

    # Parent-readable protection summary: full / reduced / rules_only.
    warnings: list[str] = []
    tier = settings.classifier_mode_resolved
    if not (vision_status.available and text_status.available):
        warnings.append("Ollama is not reachable — AI classification is offline; only deterministic rules are protecting right now.")
    else:
        if tier in ("full", "text_llm") and not text_present:
            warnings.append(f"Text model {settings.text_model} is not installed.")
        if tier in ("full", "vision") and not vision_present:
            warnings.append(f"Vision model {settings.vision_model} is not installed — image-only risks (nudity/gore/weapons) are not detected.")
    if tier in {"rules_only", "text_llm"}:
        warnings.append(f"{tier} mode: image-only risks (nudity/gore/weapons) are not detected on this hardware.")
    if not tesseract_available:
        if tier in {"rules_only", "text_llm"}:
            warnings.append(f"Tesseract OCR is not available — screenshots cannot be read at all in {tier} mode.")
        else:
            warnings.append("Tesseract OCR fallback is not available — exact phrase detection depends on vision OCR.")
    if not (vision_status.available and text_status.available):
        protection_level = "rules_only"
    elif warnings:
        protection_level = "reduced"
    else:
        protection_level = "full"

    from app.services import screenshot_async
    pending = screenshot_async.pending_count()
    throughput = snap.get("throughput", {})
    latency_basis_ms = (
        throughput.get("p95_latency_ms")
        or throughput.get("avg_latency_ms")
        or int(settings.classifier_timeout_seconds * 1000)
    )
    estimated_delay_ms = int(pending * latency_basis_ms)
    if pending >= 50 or estimated_delay_ms >= 10 * 60 * 1000:
        classification_capacity = "unhealthy"
    elif pending > 0:
        classification_capacity = "backlog"
    else:
        classification_capacity = "ok"

    return {
        "status": "ok",
        "version": __version__,
        "tier": settings.classifier_tier,
        "mode": settings.classifier_mode_resolved,
        "ocr": {
            "available": tesseract_available,
            "languages": settings.ocr_language_list,
            "recent": snap.get("ocr", {}),
        },
        "protection": {"level": protection_level, "warnings": warnings},
        "tesseract_available": tesseract_available,
        "queue": snap,
        "pending_classification": pending,
        "classification_capacity": {
            "status": classification_capacity,
            "estimated_delay_ms": estimated_delay_ms,
            "latency_basis_ms": int(latency_basis_ms),
        },
        "agent_queues": pipeline_metrics.agent_queues(),
        "ollama": {
            "url": vision_status.base_url,
            "available": vision_status.available and text_status.available,
            "error": vision_status.error or text_status.error,
            "text_model": settings.text_model,
            "text_model_present": text_present,
            "text_ollama_url": text_status.base_url,
            "text_ollama_available": text_status.available,
            "vision_model": settings.vision_model,
            "vision_model_present": vision_present,
            "vision_ollama_url": vision_status.base_url,
            "vision_ollama_available": vision_status.available,
            "all_models": sorted(set(vision_status.models) | set(text_status.models)),
        },
    }
