"""Ollama / model status + test endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import current_user
from app.db.models import User
from app.services.classifier import classify_text
from app.services.ollama_client import OllamaClient

router = APIRouter(prefix="/models", tags=["models"])


class StatusResponse(BaseModel):
    ollama_available: bool
    ollama_url: str
    models_installed: list[str]
    error: str | None


@router.get("/status", response_model=StatusResponse)
async def status(_: User = Depends(current_user)):
    client = OllamaClient()
    s = await client.status()
    return StatusResponse(
        ollama_available=s.available,
        ollama_url=s.base_url,
        models_installed=s.models,
        error=s.error,
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
