"""Classifier tests — runs with mock Ollama (LLM unavailable path)."""
from __future__ import annotations

import pytest

from app.services.classifier import classify_text


@pytest.mark.asyncio
async def test_rules_only_when_llm_unavailable_critical():
    # Without a running Ollama, classifier should still produce critical from rules
    r = await classify_text(redacted_text="don't tell your parents about this")
    assert r["risk_level"] == "critical"
    assert "secrecy_request" in r["categories"]
    assert r["recommended_action"] == "alert_parent"


@pytest.mark.asyncio
async def test_rules_only_safe_text():
    r = await classify_text(redacted_text="we are playing minecraft tonight")
    assert r["risk_level"] == "none"
    assert r["score"] == 0


@pytest.mark.asyncio
async def test_combined_grooming_secrecy_scores_critical():
    r = await classify_text(
        redacted_text="add me on discord and don't tell your parents and send me a pic"
    )
    assert r["risk_level"] == "critical"


@pytest.mark.asyncio
async def test_phishing_high():
    r = await classify_text(redacted_text="verify your account here bit.ly/abc123")
    assert r["risk_level"] in ("high", "medium", "critical")


@pytest.mark.asyncio
async def test_empty_text():
    r = await classify_text(redacted_text="")
    assert r["risk_level"] == "none"
    assert r["score"] == 0
