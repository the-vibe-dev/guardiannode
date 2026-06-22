#!/usr/bin/env python3
"""Generate and verify hardware tier constants from shared/hardware_tiers.json."""
from __future__ import annotations

import argparse
import json
import pprint
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared" / "hardware_tiers.json"
PYTHON_TARGETS = [
    ROOT / "agent-windows" / "src" / "hardware_tiers.py",
    ROOT / "backend" / "app" / "hardware_tiers.py",
]
INNO_TARGET = ROOT / "installer" / "shared" / "hardware_tiers.iss"


def _load() -> dict[str, Any]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _render_python(data: dict[str, Any]) -> str:
    rendered = pprint.pformat(data, sort_dicts=True, width=100)
    return f'''"""Generated from shared/hardware_tiers.json. Do not edit by hand."""
from __future__ import annotations

from typing import Any

HARDWARE_TIERS: dict[str, Any] = {rendered}

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
            f"GPU has {{vram}} GB VRAM - enough to keep the vision LLM and a separate text LLM available together.",
            FULL_TEXT_MODEL,
            VISION_MODEL,
            float(HARDWARE_TIERS["estimated_vram_gb"]["full"]),
        )
    if vram >= VISION_ONLY_MIN_VRAM_GB:
        return (
            "vision_only",
            f"GPU has {{vram}} GB VRAM - runs the vision model for visual risks, OCR, and text-risk classification.",
            None,
            VISION_MODEL,
            float(HARDWARE_TIERS["estimated_vram_gb"]["vision_only"]),
        )
    if ram_gb >= 8:
        return (
            "text_only",
            f"No supported vision GPU, or under {{VISION_ONLY_MIN_VRAM_GB}} GB VRAM. Using OCR plus a small text model on CPU.",
            TEXT_ONLY_MODEL,
            None,
            float(HARDWARE_TIERS["estimated_vram_gb"]["text_only"]),
        )
    return (
        "text_only",
        f"Limited RAM ({{ram_gb}} GB). Running rules/OCR only; no LLM or visual-risk model is selected automatically.",
        None,
        None,
        float(HARDWARE_TIERS["estimated_vram_gb"]["text_only"]),
    )
'''


def _pascal_string(value: str) -> str:
    return value.replace('"', '""')


def _render_inno(data: dict[str, Any]) -> str:
    models = data["models"]
    thresholds = data["thresholds"]
    return f'''; Generated from shared/hardware_tiers.json. Do not edit by hand.

#define GN_TEXT_ONLY_MIN_VRAM_GB {thresholds["text_only_min_vram_gb"]}
#define GN_VISION_ONLY_MIN_VRAM_GB {thresholds["vision_only_min_vram_gb"]}
#define GN_FULL_MIN_VRAM_GB {thresholds["full_min_vram_gb"]}
#define GN_FULL_TEXT_MODEL "{_pascal_string(models["full_text_model"])}"
#define GN_TEXT_ONLY_MODEL "{_pascal_string(models["text_only_model"])}"
#define GN_VISION_MODEL "{_pascal_string(models["vision_model"])}"
'''


def _expected() -> dict[Path, str]:
    data = _load()
    outputs = {target: _render_python(data) for target in PYTHON_TARGETS}
    outputs[INNO_TARGET] = _render_inno(data)
    return outputs


def write() -> int:
    for path, content in _expected().items():
        path.write_text(content, encoding="utf-8")
    return 0


def check() -> int:
    failures: list[str] = []
    for path, content in _expected().items():
        if not path.exists():
            failures.append(f"missing generated file: {path.relative_to(ROOT)}")
            continue
        if path.read_text(encoding="utf-8") != content:
            failures.append(f"stale generated file: {path.relative_to(ROOT)}")
    if failures:
        print("\\n".join(failures))
        print("Run: python scripts/sync_hardware_tiers.py --write")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return write() if args.write else check()


if __name__ == "__main__":
    raise SystemExit(main())
