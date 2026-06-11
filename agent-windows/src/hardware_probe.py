"""Detect hardware tier for installer model + classifier recommendation.

Output drives the installer's choice of:
- classifier_tier (full / vision_only / text_only)
- which Ollama models to pull
- whether to bundle Tesseract for the CPU path
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass
class HardwareInfo:
    os: str
    cpu_cores: int
    ram_gb: int
    gpu_vendor: str | None
    gpu_name: str | None
    gpu_vram_gb: int | None
    # GuardianNode tier: full / vision_only / text_only
    classifier_tier: str
    # Models the installer should pull (Ollama tags)
    text_model: str | None      # used in full + text_only tiers
    vision_model: str | None    # used in full + vision_only tiers
    # Total estimated VRAM the chosen tier uses (informational)
    estimated_vram_gb: float
    # Reasoning for the chosen tier (shown to parent in installer)
    reasoning: str


def _ram_gb() -> int:
    try:
        import psutil
        return max(1, int(round(psutil.virtual_memory().total / (1024 ** 3))))
    except Exception:
        return 4


def _detect_gpu() -> tuple[str | None, str | None, int | None]:
    """Returns (vendor, name, vram_gb). Best-effort.

    For multi-GPU systems we return the LARGEST single GPU's VRAM, since
    Ollama loads each model on one GPU at a time.
    """
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            out = subprocess.run(
                [nvidia, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            best_vram = 0
            best_name: str | None = None
            for line in (out.stdout or "").strip().splitlines():
                try:
                    name, mem = [p.strip() for p in line.split(",", 1)]
                    vram_mb = int(mem)
                    vram_gb = max(1, vram_mb // 1024)
                    if vram_gb > best_vram:
                        best_vram = vram_gb
                        best_name = name
                except Exception:
                    continue
            if best_name:
                return "nvidia", best_name, best_vram
        except Exception:
            pass
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController | Select -First 1).Name"],
                capture_output=True, text=True, timeout=5,
            )
            name = (out.stdout or "").strip().splitlines()[-1] if out.stdout else ""
            if name and name.lower() != "name":
                vendor = "amd" if "AMD" in name or "Radeon" in name else (
                    "intel" if "Intel" in name else "unknown"
                )
                # No reliable VRAM from WMI on non-NVIDIA; assume small.
                return vendor, name, None
        except Exception:
            pass
    return None, None, None


# Tier selection thresholds (VRAM in GB). Sizes are the REAL hot footprint:
# qwen2.5vl:7b is ~7.5 GB of weights PLUS a ~3-4 GB compute-graph/KV workspace
# at num_ctx=4096, so it needs the better part of a 12 GB card on its own.
#
#   vision_only: qwen2.5vl:7b — the standard GPU path. The vision model does
#                OCR, image classification (nudity/gore/weapons/etc.), AND
#                text-risk classification (grooming/self-harm/scam) in one call.
#                Needs ~6 GB+; comfortable on 8-12 GB.
#   full:        vision LLM + a separate text LLM kept hot together. This does
#                NOT fit on a single 12 GB GPU (the vision model alone wants
#                ~11 GB). Only auto-selected at 16 GB+; otherwise it thrashes
#                VRAM and the vision model errors out. vision_only already
#                covers text, so full is a marginal second-opinion upgrade.
#   text_only:   no/low-VRAM GPU. Tesseract OCR + a small text LLM on CPU. This
#                is the no-GPU fallback and CANNOT see visual-only risks
#                (nudity/gore in images without on-screen text).
def _select_tier(ram_gb: int, vram_gb: int | None) -> tuple[str, str, str | None, str | None, float]:
    v = vram_gb or 0
    if v >= 16:
        return (
            "full",
            f"GPU has {v} GB VRAM — enough to keep the vision LLM and a separate text "
            "LLM hot together for a second opinion on extracted text.",
            "llama3.2:3b",
            "qwen2.5vl:7b",
            13.0,
        )
    if v >= 6:
        return (
            "vision_only",
            f"GPU has {v} GB VRAM — runs the vision model, which detects visual risks "
            "(nudity, gore, weapons, etc.), reads the on-screen text (OCR), and classifies "
            "that text (grooming, self-harm, scams) in a single pass. Full coverage.",
            None,
            "qwen2.5vl:7b",
            11.0,
        )
    if ram_gb >= 8:
        return (
            "text_only",
            "No GPU (or under 6 GB VRAM). Lower-power path: Tesseract OCR + a small text "
            "LLM on the CPU, plus the rules engine. It reads and classifies on-screen TEXT "
            "only — visual-only risks (nudity/gore/weapons in images without captions) will "
            "NOT be detected. For full coverage, pair this PC with a GPU-enabled GuardianNode "
            "server.",
            "llama3.2:1b",
            None,
            0.0,
        )
    # <8 GB RAM is below our supported floor
    return (
        "text_only",
        f"Limited RAM ({ram_gb} GB). Running the rules engine only — no LLM. "
        "Detection will catch deterministic patterns but not nuanced grooming or any "
        "visual risks.",
        None,
        None,
        0.0,
    )


def probe() -> HardwareInfo:
    cores = max(1, os.cpu_count() or 1)
    ram = _ram_gb()
    vendor, name, vram = _detect_gpu()
    tier, reasoning, text_model, vision_model, vram_est = _select_tier(ram, vram)
    return HardwareInfo(
        os=platform.system().lower(),
        cpu_cores=cores,
        ram_gb=ram,
        gpu_vendor=vendor,
        gpu_name=name,
        gpu_vram_gb=vram,
        classifier_tier=tier,
        text_model=text_model,
        vision_model=vision_model,
        estimated_vram_gb=vram_est,
        reasoning=reasoning,
    )


def cli() -> None:
    """Called by the Inno Setup wizard via Exec'd PowerShell wrapper.
    Prints JSON the wizard parses to drive model pulls + env-var writes.
    """
    info = probe()
    print(json.dumps(asdict(info), indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
