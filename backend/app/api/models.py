"""Ollama / model status + test endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import current_user
from app.db.models import User
from app.services.classifier import classify_text
from app.services.ollama_client import OllamaClient
from app.settings import settings

router = APIRouter(prefix="/models", tags=["models"])

# What each detection tier actually does, for the dashboard explainer.
TIER_INFO = {
    "full": {
        "label": "Full (GPU, 16 GB+)",
        "detects_images": True,
        "detects_text": True,
        "summary": "Vision model (images + on-screen text) plus a separate text "
                   "model for a second opinion on extracted text.",
    },
    "vision_only": {
        "label": "Vision (GPU)",
        "detects_images": True,
        "detects_text": True,
        "summary": "The vision model detects visual risks (nudity, gore, weapons, "
                   "etc.), reads the on-screen text, and classifies that text "
                   "(grooming, self-harm, scams) in a single pass. Full coverage.",
    },
    "text_only": {
        "label": "Text only (no GPU)",
        "detects_images": False,
        "detects_text": True,
        "summary": "Lower-power path for machines without a capable GPU: Tesseract "
                   "OCR + a small text model on the CPU. Reads and classifies "
                   "on-screen TEXT only — visual-only risks (nudity/gore/weapons in "
                   "images without captions) are NOT detected. Pair with a "
                   "GPU-enabled server for full coverage.",
    },
}


class StatusResponse(BaseModel):
    ollama_available: bool
    ollama_url: str
    models_installed: list[str]
    error: str | None
    tier: str
    tier_info: dict
    vision_model: str
    text_model: str


@router.get("/status", response_model=StatusResponse)
async def status(_: User = Depends(current_user)):
    client = OllamaClient()
    s = await client.status()
    tier = settings.classifier_tier
    return StatusResponse(
        ollama_available=s.available,
        ollama_url=s.base_url,
        models_installed=s.models,
        error=s.error,
        tier=tier,
        tier_info=TIER_INFO.get(tier, TIER_INFO["vision_only"]),
        vision_model=settings.vision_model,
        text_model=settings.text_model,
    )


class TestRequest(BaseModel):
    text: str = "Add me on snap and don't tell your parents"


class TestResponse(BaseModel):
    risk_level: str
    score: int
    categories: list[str]
    summary: str
    model: str | None
    rules_triggered: list[str]


@router.post("/test", response_model=TestResponse)
async def test_classification(req: TestRequest, _: User = Depends(current_user)):
    r = await classify_text(redacted_text=req.text)
    return TestResponse(
        risk_level=r["risk_level"],
        score=r["score"],
        categories=r["categories"],
        summary=r["summary"],
        model=r["model"],
        rules_triggered=r["rules_triggered"],
    )
