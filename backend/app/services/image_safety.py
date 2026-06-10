"""Image safety classification via Ollama vision model."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.services.ollama_client import OllamaClient, OllamaError
from app.settings import settings

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "vision_classifier.txt"
_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _prompt_version() -> str:
    return hashlib.sha256(_prompt().encode("utf-8")).hexdigest()[:8]


def _extract_json(s: str) -> dict[str, Any] | None:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        m = _JSON_RE.search(s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


async def classify_image(
    *,
    image_bytes: bytes,
    app_name: str | None = None,
    source_type: str = "image",
    age_group: str = "10_13",
    timestamp: str = "",
    related_ocr_text: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    chosen = model or settings.vision_model
    client = OllamaClient(base_url=settings.vision_ollama_url_resolved, timeout=120.0)
    prompt = _prompt().format(
        app_name=app_name or "unknown",
        source_type=source_type,
        age_group=age_group,
        timestamp=timestamp,
        related_ocr_text=related_ocr_text[:1024] or "none",
    )

    result: dict[str, Any] = {
        "visible_text": "",
        "persons_visible": False,
        "apparent_minor": False,
        "risk_level": "none",
        "score": 0,
        "categories": [],
        "summary": "",
        "visual_evidence": [],
        "recommended_action": "none",
        "confidence": 0.0,
        "false_positive_notes": "",
        "model": None,
        "prompt_version": _prompt_version(),
    }

    try:
        response = await client.generate(
            model=chosen,
            prompt=prompt,
            images=[image_bytes],
            # num_ctx 4096 keeps KV-cache footprint small enough that a small
            # text LLM (e.g. llama3.2:3b ~2.6 GB) can co-reside on a 12 GB GPU.
            options={"temperature": 0.1, "num_ctx": 4096},
            format_json=True,
        )
        parsed = _extract_json(response)
        if parsed is None:
            return result
        result.update(parsed)
        result["model"] = chosen
        # Normalize
        if result["risk_level"] not in {"none", "low", "medium", "high", "critical"}:
            result["risk_level"] = "none"
        try:
            result["score"] = max(0, min(100, int(result.get("score", 0))))
        except Exception:
            result["score"] = 0
        # Truncate visible_text to a sane max for downstream storage
        if isinstance(result.get("visible_text"), str):
            result["visible_text"] = result["visible_text"][:16384]
        else:
            result["visible_text"] = ""
    except OllamaError as e:
        log.warning("vision classifier ollama error: %s", e)
    except Exception as e:
        log.warning("vision classifier error: %s", e)
    return result
