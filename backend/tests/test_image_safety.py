from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_vision_retries_when_context_is_exhausted(monkeypatch):
    from app.services import image_safety
    from app.services.ollama_client import OllamaClient, OllamaContextLengthError

    contexts: list[int] = []

    async def fake_generate(self, **kwargs):
        num_ctx = kwargs["options"]["num_ctx"]
        contexts.append(num_ctx)
        if len(contexts) == 1:
            raise OllamaContextLengthError("context exhausted")
        return (
            '{"visible_text":"Customer: Kale","risk_level":"high","score":80,'
            '"categories":["custom_watch"],"recommended_action":"alert_parent"}'
        )

    monkeypatch.setattr(image_safety.settings, "vision_num_ctx", 4096)
    monkeypatch.setattr(OllamaClient, "generate", fake_generate)

    result = await image_safety.classify_image(image_bytes=b"not-a-real-image")

    assert contexts == [4096, 8192]
    assert result["visible_text"] == "Customer: Kale"
    assert result["risk_level"] == "high"
    assert result["model"] == image_safety.settings.vision_model
