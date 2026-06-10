"""HTTP client for a local Ollama server.

Used by the text classifier and the vision classifier. Gracefully degrades if
Ollama is unavailable so the rest of the system keeps working.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.settings import settings

log = logging.getLogger(__name__)


@dataclass
class OllamaStatus:
    available: bool
    base_url: str
    models: list[str]
    error: str | None = None


class OllamaError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = timeout

    async def status(self) -> OllamaStatus:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return OllamaStatus(available=True, base_url=self.base_url, models=models)
        except Exception as e:
            return OllamaStatus(available=False, base_url=self.base_url, models=[], error=str(e))

    async def list_models(self) -> list[str]:
        s = await self.status()
        return s.models

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        images: list[bytes] | None = None,
        options: dict | None = None,
        format_json: bool = False,
        keep_alive: str = "24h",
    ) -> str:
        """Single-shot text completion. Returns the full response text.

        If `format_json=True`, asks Ollama for JSON-formatted output (supported
        by recent Ollama versions).

        `keep_alive` pins the model in VRAM for the given duration. Default 24h
        keeps the model hot so subsequent calls don't pay cold-load. Pair with
        OLLAMA_MAX_LOADED_MODELS>=2 on the server when running multiple models
        concurrently (e.g. vision + small text LLM at the same time).
        """
        body: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            # Disable model "thinking" mode (Qwen3/Qwen3.5/DeepSeek-R1) so the
            # JSON answer lands in `response` instead of `thinking`.
            "think": False,
            "keep_alive": keep_alive,
        }
        if system:
            body["system"] = system
        if options:
            body["options"] = options
        if format_json:
            body["format"] = "json"
        if images:
            body["images"] = [base64.b64encode(img).decode("ascii") for img in images]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/api/generate", json=body)
                r.raise_for_status()
                data = r.json()
                # Some models (Qwen3.x) emit JSON in the `thinking` field if
                # think mode is on; fall back to that when response is empty.
                return data.get("response") or data.get("thinking") or ""
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama HTTP error: {e}") from e

    async def generate_with_image_path(
        self,
        *,
        model: str,
        prompt: str,
        image_path: Path,
        system: str | None = None,
        options: dict | None = None,
        format_json: bool = False,
    ) -> str:
        img_bytes = Path(image_path).read_bytes()
        return await self.generate(
            model=model,
            prompt=prompt,
            system=system,
            images=[img_bytes],
            options=options,
            format_json=format_json,
        )

    async def pull(self, model: str) -> None:
        """Pull a model. Note: streaming progress is not exposed here."""
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/pull", json={"name": model, "stream": True}
                ) as r:
                    async for _ in r.aiter_lines():
                        pass
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama pull failed: {e}") from e
