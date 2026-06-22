from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hardware_tier_source_thresholds_are_conservative() -> None:
    data = json.loads((ROOT / "shared" / "hardware_tiers.json").read_text(encoding="utf-8"))

    assert data["thresholds"] == {
        "text_only_min_vram_gb": 0,
        "vision_only_min_vram_gb": 12,
        "full_min_vram_gb": 16,
    }
    assert data["models"]["vision_model"] == "qwen3-vl:8b-instruct"


def test_generated_hardware_tier_outputs_are_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/sync_hardware_tiers.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
