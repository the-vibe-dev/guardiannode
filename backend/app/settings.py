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
        env_file=(".env", _default_data_dir() / "server.env"),
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
    session_idle_timeout_seconds: int = 60 * 60
    session_absolute_timeout_seconds: int = 7 * 24 * 60 * 60
    recent_auth_timeout_seconds: int = 15 * 60
    setup_token_ttl_seconds: int = 24 * 60 * 60
    https_only_cookies: bool = False
    mdns_enabled: bool = True
    cors_allow_origin: str | None = None  # for dashboard dev server
    allowed_hosts: str = "127.0.0.1,localhost,::1,testserver"
    text_model: str = "llama3.2:3b"
    # qwen2.5vl:7b is fast (~2-3s warm per frame at the settings below) and reads
    # on-screen text + classifies images in one pass. It nominally offloads ~2 GB
    # to CPU on a 12 GB card, but that does not hurt warm latency; the earlier
    # OOM *crashes* came from too-large a context/image (see vision_num_ctx +
    # vision_max_image_edge), not the model itself. qwen3-vl:8b fits fully but is
    # markedly slower per frame, so it's not the default.
    # qwen3-vl:8b fits FULLY on a 12 GB GPU (~7.6 GB, no CPU offload), unlike
    # qwen2.5vl:7b whose ~7.5 GB vision compute graph pushed it to ~14 GB and
    # OOM-crashed the runner. The client already disables Qwen3 "thinking" mode
    # (think:false), so it's fast as well as crash-free.
    # qwen3-vl:8b-INSTRUCT (not the default thinking variant) — fits fully on a
    # 12 GB GPU (~7.6 GB, no CPU offload), returns clean single-shot JSON, and
    # runs ~4-5s warm. The plain `qwen3-vl:8b` tag is the *thinking* variant,
    # whose reasoning output goes to a separate field leaving `response` empty
    # (Ollama bug ollama/ollama#14798) — do not use it. qwen2.5vl:7b also works
    # but offloads ~2 GB to CPU and runs ~30s.
    vision_model: str = "qwen3-vl:8b-instruct"
    # Full-screen OCR can itself be several thousand tokens. 4096 truncated
    # otherwise-valid JSON on real 1600x900 desktop frames.
    vision_num_ctx: int = 8192
    classifier_timeout_seconds: int = 30
    ollama_status_timeout_seconds: int = 5
    ollama_pull_timeout_seconds: int = 1800
    rules_version: str = "0.1.0-alpha.1"
    # Classifier tier: governs which paths run per screenshot.
    #  "full"        — vision LLM + text LLM hot together; needs 16+ GB VRAM
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
    # Tamper / offline detection. A child who is a local admin can kill the
    # agent or shut the PC down; the watchdog auto-restarts it, but if the
    # backend stops hearing heartbeats we raise an alert so the parent knows
    # monitoring stopped. Agent heartbeats every 30s.
    device_offline_alert_enabled: bool = True
    device_offline_after_seconds: int = 180
    device_offline_check_interval_seconds: int = 60
    notification_worker_enabled: bool = True
    notification_worker_interval_seconds: int = 10
    # Safety cap on the long edge (px) sent to the vision model. qwen3-vl:8b has
    # ~4.6 GB headroom on a 12 GB card, so full-res frames OCR best and are left
    # untouched; this only shrinks enormous 4K+ frames. Downscaling degrades OCR
    # of small text (usernames, handles, addresses) — measured. 0 disables it.
    vision_max_image_edge: int = 2560

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

    def effective_allowed_hosts(self) -> list[str]:
        configured = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        if configured == ["*"]:
            if self.dev_mode:
                return ["*"]
            configured = []
        hosts = configured or ["127.0.0.1", "localhost", "::1", "testserver"]
        if self.bind_host not in {"0.0.0.0", "::", ""}:
            hosts.append(self.bind_host)
        return list(dict.fromkeys(hosts))

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.keys_dir, self.evidence_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
