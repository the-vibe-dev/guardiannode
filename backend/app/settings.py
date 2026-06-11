"""Settings for the GuardianNode backend."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode"
    return Path.home() / ".guardiannode"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GUARDIANNODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = _default_data_dir()
    bind_host: str = "127.0.0.1"
    bind_port: int = 8787
    ollama_url: str = "http://127.0.0.1:11434"
    # Optional per-role overrides — set these if vision and text LLM should use
    # different Ollama instances (e.g. on different ports / GPUs).
    # Defaults to ollama_url if unset. Lets you keep both models hot at once
    # by routing each role to its own Ollama process.
    vision_ollama_url: str | None = None
    text_ollama_url: str | None = None
    db_url: str | None = None
    log_level: str = "INFO"
    dev_mode: bool = False
    session_secret: str | None = None  # auto-generated on first run
    mdns_enabled: bool = True
    cors_allow_origin: str | None = None  # for dashboard dev server
    text_model: str = "llama3.2:3b"
    vision_model: str = "llava-phi3"
    classifier_timeout_seconds: int = 30
    rules_version: str = "0.1.0"
    # Classifier tier: governs which paths run per screenshot.
    #  "full"        — vision LLM (qwen2.5vl) + text LLM (llama3.2:3b) hot together; needs 10+ GB VRAM
    #  "vision_only" — vision LLM only; needs 6+ GB VRAM
    #  "text_only"   — Tesseract OCR + small text LLM (llama3.2:1b) on CPU; no GPU required
    classifier_tier: str = "vision_only"
    # Used in text_only tier and as fallback OCR when vision LLM unavailable.
    tesseract_enabled: bool = True
    retention_cleanup_enabled: bool = True
    retention_cleanup_interval_seconds: int = 3600
    # Identical open findings (same device/profile/severity/categories) within
    # this window fold into one alert with a repeat count instead of flooding
    # the Risk Feed. 0 disables aggregation.
    alert_dedup_window_seconds: int = 1800

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_url_resolved(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite:///{self.data_dir / 'guardiannode.db'}"

    @property
    def vision_ollama_url_resolved(self) -> str:
        return self.vision_ollama_url or self.ollama_url

    @property
    def text_ollama_url_resolved(self) -> str:
        return self.text_ollama_url or self.ollama_url

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.keys_dir, self.evidence_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
