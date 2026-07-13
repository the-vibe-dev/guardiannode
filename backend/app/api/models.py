"""Ollama / model status + test endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user
from app.db.models import User
from app.hardware_tiers import TIER_INFO
from app.services.classifier import classify_text
from app.services.ollama_client import OllamaClient
from app.settings import settings

router = APIRouter(prefix="/models", tags=["models"])

class StatusResponse(BaseModel):
    ollama_available: bool
    ollama_url: str
    models_installed: list[str]
    error: str | None
    vision_ollama_url: str
    vision_ollama_available: bool
    vision_models_installed: list[str]
    text_ollama_url: str
    text_ollama_available: bool
    text_models_installed: list[str]
    tier: str
    tier_info: dict
    vision_model: str
    text_model: str


@router.get("/status", response_model=StatusResponse)
async def status(_: User = Depends(current_user)):
    vision_url = settings.vision_ollama_url_resolved
    text_url = settings.text_ollama_url_resolved
    vision_client = OllamaClient(base_url=vision_url)
    if text_url == vision_url:
        vision_status = await vision_client.status()
        text_status = vision_status
    else:
        text_client = OllamaClient(base_url=text_url)
        vision_status = await vision_client.status()
        text_status = await text_client.status()
    tier = settings.classifier_mode_resolved
    all_models = sorted(set(vision_status.models) | set(text_status.models))
    return StatusResponse(
        ollama_available=(
            text_status.available if tier == "text_llm"
            else vision_status.available if tier == "vision"
            else vision_status.available and text_status.available if tier == "full"
            else True
        ),
        ollama_url=vision_status.base_url,
        models_installed=all_models,
        error=vision_status.error or text_status.error,
        vision_ollama_url=vision_status.base_url,
        vision_ollama_available=vision_status.available,
        vision_models_installed=vision_status.models,
        text_ollama_url=text_status.base_url,
        text_ollama_available=text_status.available,
        text_models_installed=text_status.models,
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
