"""Model unavailability must degrade loudly, never silently report 'safe'."""
from __future__ import annotations

import pytest

from app.db.models import Device, RiskResult


@pytest.fixture
def ollama_unavailable(monkeypatch):
    from app.services.ollama_client import OllamaClient, OllamaError

    async def fail_generate(self, **kwargs):
        raise OllamaError("test model unavailable")

    monkeypatch.setattr(OllamaClient, "generate", fail_generate)


@pytest.mark.asyncio
async def test_llm_failure_marks_unclassified_status(ollama_unavailable):
    """When Ollama is unreachable, status flags the reduced protection."""
    from app.services import classifier

    # No Ollama in tests: the call fails fast with a connection error.
    result = await classifier.classify_text(redacted_text="totally ordinary text")
    assert result["status"] == "unclassified_model_unavailable"
    assert result["model"] is None
    # Severity stays whatever the rules said (here: none) — but the status
    # makes clear no model vouched for it.
    assert result["risk_level"] == "none"


@pytest.mark.asyncio
async def test_llm_failure_still_applies_rules(ollama_unavailable):
    from app.services import classifier

    result = await classifier.classify_text(redacted_text="free robux click here now")
    assert result["status"] == "unclassified_model_unavailable"
    assert result["risk_level"] == "high"
    assert "scam" in result["categories"]


@pytest.mark.asyncio
async def test_status_persisted_on_risk_result(db_session, ollama_unavailable):
    from app.services import event_ingest

    db_session.add(Device(device_id="dev1", hostname="kid-pc", paired=True))
    db_session.commit()

    result = await event_ingest.ingest_event(
        db_session,
        payload={"source_type": "ocr", "redacted_text": "hello there"},
        device_id="dev1",
    )
    db_session.commit()
    rr = db_session.get(RiskResult, result["risk_id"])
    assert rr.classifier_status == "unclassified_model_unavailable"


@pytest.mark.asyncio
async def test_successful_llm_marks_ok(monkeypatch):
    from app.services import classifier
    from app.services.ollama_client import OllamaClient

    async def good_generate(self, **kwargs):
        return '{"risk_level": "none", "score": 0, "categories": [], "summary": "fine"}'

    monkeypatch.setattr(OllamaClient, "generate", good_generate)
    result = await classifier.classify_text(redacted_text="homework about volcanoes")
    assert result["status"] == "ok"
    assert result["model"] is not None
