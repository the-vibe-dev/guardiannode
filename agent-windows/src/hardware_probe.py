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

try:
    from .hardware_tiers import select_tier
except ImportError:  # pragma: no cover - direct script execution by installers
    from hardware_tiers import select_tier


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
        registry_gpu = _detect_windows_gpu_registry()
        if registry_gpu[0] is not None:
            return registry_gpu
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


def _detect_windows_gpu_registry() -> tuple[str | None, str | None, int | None]:
    """Read Windows display-adapter registry metadata when NVML is unavailable."""
    command = r"""
$bestName = ""
$bestBytes = 0
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue | ForEach-Object {
  $p = Get-ItemProperty $_.PsPath -ErrorAction SilentlyContinue
  if ($p.DriverDesc -match 'NVIDIA') {
    $bytes = 0
    if ($p.'HardwareInformation.qwMemorySize') {
      $bytes = [int64]$p.'HardwareInformation.qwMemorySize'
    } elseif ($p.'HardwareInformation.MemorySize') {
      $bytes = [int64][uint32]$p.'HardwareInformation.MemorySize'
    }
    if ($bytes -gt $bestBytes) {
      $bestBytes = $bytes
      $bestName = [string]$p.DriverDesc
    }
  }
}
if ($bestName) {
  [pscustomobject]@{ name = $bestName; vram_gb = [int][math]::Floor($bestBytes / 1GB) } | ConvertTo-Json -Compress
}
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
        )
        payload = json.loads((out.stdout or "").strip() or "{}")
        name = payload.get("name")
        vram_gb = payload.get("vram_gb")
        if isinstance(name, str) and name and isinstance(vram_gb, int) and vram_gb > 0:
            return "nvidia", name, vram_gb
    except Exception:
        pass
    return None, None, None


def probe() -> HardwareInfo:
    cores = max(1, os.cpu_count() or 1)
    ram = _ram_gb()
    vendor, name, vram = _detect_gpu()
    tier, reasoning, text_model, vision_model, vram_est = select_tier(ram, vram)
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
