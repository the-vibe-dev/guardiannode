"""Health endpoint — no auth, useful for installer self-tests + dashboard live status."""
from __future__ import annotations

from fastapi import APIRouter, Depends

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
    tier = settings.classifier_tier
    if not (vision_status.available and text_status.available):
        warnings.append("Ollama is not reachable — AI classification is offline; only deterministic rules are protecting right now.")
    else:
        if tier in ("full", "text_only") and not text_present:
            warnings.append(f"Text model {settings.text_model} is not installed.")
        if tier in ("full", "vision_only") and not vision_present:
            warnings.append(f"Vision model {settings.vision_model} is not installed — image-only risks (nudity/gore/weapons) are not detected.")
    if tier == "text_only":
        warnings.append("text_only tier: image-only risks (nudity/gore/weapons) are not detected on this hardware.")
    if not tesseract_available:
        if tier == "text_only":
            warnings.append("Tesseract OCR is not available — screenshots cannot be read at all in text_only tier.")
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
