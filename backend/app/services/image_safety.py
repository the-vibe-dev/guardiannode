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


def _downscale_for_vision(image_bytes: bytes, max_edge: int | None = None) -> bytes:
    """Shrink the screenshot to a sane resolution for the vision model.

    A full-res screenshot turns into a huge number of vision tokens, which
    inflates the compute-graph/KV footprint and can push qwen2.5vl past a
    12 GB GPU (→ Ollama 500 / OOM) and slows inference. Screen text stays
    legible at ~1280px, which is plenty for classification. Only the model's
    input copy is shrunk — the stored evidence blob keeps full resolution.
    """
    max_edge = max_edge or settings.vision_max_image_edge
    if max_edge <= 0:
        return image_bytes
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_edge:
            return image_bytes
        scale = max_edge / float(max(w, h))
        img = img.convert("RGB").resize((max(1, int(w * scale)), max(1, int(h * scale))))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        log.debug("vision downscale failed (%s); sending original", e)
        return image_bytes


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
    watch_phrases: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    chosen = model or settings.vision_model
    client = OllamaClient(base_url=settings.vision_ollama_url_resolved, timeout=120.0)
    phrases = [p.strip() for p in (watch_phrases or []) if p and p.strip()]
    watch_str = "; ".join(f'"{p}"' for p in phrases) if phrases else "none"
    prompt = _prompt().format(
        app_name=app_name or "unknown",
        source_type=source_type,
        age_group=age_group,
        timestamp=timestamp,
        related_ocr_text=related_ocr_text[:1024] or "none",
        watch_phrases=watch_str,
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

    vision_image = _downscale_for_vision(image_bytes)

    try:
        response = await client.generate(
            model=chosen,
            prompt=prompt,
            images=[vision_image],
            # num_ctx bounds the vision compute-graph size (the thing that OOM'd
            # qwen2.5vl on big frames). See settings.vision_num_ctx.
            options={"temperature": 0.1, "num_ctx": settings.vision_num_ctx},
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
