"""Agent config loading from YAML."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def default_config_path() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode" / "agent.yaml"
    return Path.home() / ".guardiannode" / "agent.yaml"


def default_device_path() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode" / "device.json"
    return Path.home() / ".guardiannode" / "device.json"


@dataclass
class AgentConfig:
    backend_url: str = "http://127.0.0.1:8787"
    device_id: str = ""
    device_token: str = ""
    profile_id: str | None = None
    age_group: str = "10_13"
    policy_id: str = "default"
    policy_version: str = "0.1.0-alpha.1"
    ocr_engine: str = "tesseract"  # tesseract | paddle | none
    # Capture cadence. The phash is now computed on the foreground-window
    # region, so it correctly detects small text edits (e.g. lines added in
    # Notepad) instead of treating them as identical full-screen frames.
    # Effective send rate is still gated by phash dedup, so a tight cadence
    # doesn't flood the backend on idle screens.
    ocr_cadence_seconds: int = 5
    ocr_min_confidence: float = 0.5
    # Perceptual hash Hamming threshold over the active-window dHash.
    # 2 catches a single-line text edit; 0-1 catches even cursor blink (too noisy).
    phash_threshold: int = 2
    # Whole-screen change trigger (Hamming over the 256-bit full-frame dHash).
    # Catches a background window loading new content while the foreground
    # window is unchanged (e.g. a browser behind Notepad). Keep above the
    # duplicate threshold so clock ticks / cursor noise don't trigger.
    full_screen_change_threshold: int = 10
    # Force a fresh frame even when perceptual hashing misses tiny text
    # edits. The live capture policy may shorten the normal cadence, while this
    # bounds the longest period without a frame from the visible desktop.
    max_capture_interval_seconds: int = 15
    # Default to the visible desktop so typed risk in simple apps such as
    # Notepad is still reviewed. App names remain useful context, not a gate.
    full_screen_capture_enabled: bool = True
    monitored_apps: list[str] = field(default_factory=lambda: [
        "Roblox.exe", "Discord.exe", "notepad.exe", "chrome.exe", "msedge.exe",
        "firefox.exe", "brave.exe", "outlook.exe", "Teams.exe",
        "Steam.exe", "EpicGamesLauncher.exe", "MinecraftLauncher.exe",
        "javaw.exe", "putty.exe", "WindowsTerminal.exe", "wt.exe",
    ])
    log_level: str = "INFO"
    dry_run: bool = False

    @classmethod
    def from_path(cls, path: Path) -> "AgentConfig":
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text("utf-8")) or {}
        # accept unknown keys gracefully
        kwargs = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**kwargs)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        out = {k: getattr(self, k) for k in self.__dataclass_fields__}
        path.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
