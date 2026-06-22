"""Generated from shared/hardware_tiers.json. Do not edit by hand."""
from __future__ import annotations

from typing import Any

HARDWARE_TIERS: dict[str, Any] = {'estimated_vram_gb': {'full': 13.0, 'text_only': 0.0, 'vision_only': 11.0},
 'models': {'full_text_model': 'llama3.2:3b',
            'text_only_model': 'llama3.2:1b',
            'vision_model': 'qwen3-vl:8b-instruct'},
 'schema_version': 1,
 'thresholds': {'full_min_vram_gb': 16, 'text_only_min_vram_gb': 0, 'vision_only_min_vram_gb': 12},
 'tiers': {'full': {'detects_images': True,
                    'detects_text': True,
                    'hardware': 'NVIDIA GPU, 16+ GB VRAM or split endpoints',
                    'label': 'Full (GPU, 16 GB+)',
                    'summary': 'Vision model for screenshots plus a separate text model for a '
                               'second opinion on extracted text.'},
           'text_only': {'detects_images': False,
                         'detects_text': True,
                         'hardware': 'No GPU or under 12 GB VRAM; 8+ GB RAM recommended',
                         'label': 'Text only (no/low VRAM)',
                         'summary': 'Tesseract OCR plus a small text model on CPU where possible. '
                                    'Visual-only risks may be missed.'},
           'vision_only': {'detects_images': True,
                           'detects_text': True,
                           'hardware': 'NVIDIA GPU, 12-15 GB VRAM',
                           'label': 'Vision (GPU, 12 GB+)',
                           'summary': 'The vision model detects visual risks, reads on-screen '
                                      'text, and classifies text-risk signals in one pass.'}}}

THRESHOLDS = HARDWARE_TIERS["thresholds"]
MODELS = HARDWARE_TIERS["models"]
TIER_INFO = HARDWARE_TIERS["tiers"]

TEXT_ONLY_MIN_VRAM_GB = int(THRESHOLDS["text_only_min_vram_gb"])
VISION_ONLY_MIN_VRAM_GB = int(THRESHOLDS["vision_only_min_vram_gb"])
FULL_MIN_VRAM_GB = int(THRESHOLDS["full_min_vram_gb"])
VISION_MODEL = str(MODELS["vision_model"])
FULL_TEXT_MODEL = str(MODELS["full_text_model"])
TEXT_ONLY_MODEL = str(MODELS["text_only_model"])


def select_tier(ram_gb: int, vram_gb: int | None) -> tuple[str, str, str | None, str | None, float]:
    vram = vram_gb or 0
    if vram >= FULL_MIN_VRAM_GB:
        return (
            "full",
            f"GPU has {vram} GB VRAM - enough to keep the vision LLM and a separate text LLM available together.",
            FULL_TEXT_MODEL,
            VISION_MODEL,
            float(HARDWARE_TIERS["estimated_vram_gb"]["full"]),
        )
    if vram >= VISION_ONLY_MIN_VRAM_GB:
        return (
            "vision_only",
            f"GPU has {vram} GB VRAM - runs the vision model for visual risks, OCR, and text-risk classification.",
            None,
            VISION_MODEL,
            float(HARDWARE_TIERS["estimated_vram_gb"]["vision_only"]),
        )
    if ram_gb >= 8:
        return (
            "text_only",
            f"No supported vision GPU, or under {VISION_ONLY_MIN_VRAM_GB} GB VRAM. Using OCR plus a small text model on CPU.",
            TEXT_ONLY_MODEL,
            None,
            float(HARDWARE_TIERS["estimated_vram_gb"]["text_only"]),
        )
    return (
        "text_only",
        f"Limited RAM ({ram_gb} GB). Running rules/OCR only; no LLM or visual-risk model is selected automatically.",
        None,
        None,
        float(HARDWARE_TIERS["estimated_vram_gb"]["text_only"]),
    )
