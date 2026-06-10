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

    return {
        "status": "ok",
        "version": __version__,
        "tier": settings.classifier_tier,
        "queue": snap,
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
