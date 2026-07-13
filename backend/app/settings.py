"""Settings for the GuardianNode backend."""
from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


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
    # qwen3-vl:8b-INSTRUCT is the alpha vision default. The hardware selector
    # only auto-selects vision at 12+ GB VRAM because hot model/runtime memory
    # needs substantial headroom beyond raw weight size.
    vision_model: str = "qwen3-vl:8b-instruct"
    # Full-screen OCR can itself be several thousand tokens. 4096 truncated
    # otherwise-valid JSON on real 1600x900 desktop frames.
    vision_num_ctx: int = 8192
    classifier_timeout_seconds: int = 30
    ollama_status_timeout_seconds: int = 5
    ollama_pull_timeout_seconds: int = 1800
    rules_version: str = "0.1.0-alpha.1"
    # Classifier mode: explicit capability contract for readiness and ingest.
    # The legacy classifier_tier variable remains accepted through the beta.
    classifier_mode: str | None = None
    # Legacy classifier tier: governs which paths run per screenshot.
    #  "full"        — vision LLM + text LLM hot together; needs 16+ GB VRAM
    #  "vision_only" — vision LLM only; needs 12+ GB VRAM
    #  "text_only"   — Tesseract OCR + small text LLM (llama3.2:1b) on CPU; no GPU required
    classifier_tier: str = "text_only"
    # Used in text_only tier and as fallback OCR when vision LLM unavailable.
    tesseract_enabled: bool = True
    ocr_languages: str = "eng"
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
    database_backup_enabled: bool = True
    database_backup_interval_seconds: int = 24 * 60 * 60
    database_backup_keep: int = 7
    readiness_min_free_bytes: int = 256 * 1024 * 1024
    # Safety cap on the long edge (px) sent to the vision model. qwen3-vl:8b has
    # ~4.6 GB headroom on a 12 GB card, so full-res frames OCR best and are left
    # untouched; this only shrinks enormous 4K+ frames. Downscaling degrades OCR
    # of small text (usernames, handles, addresses) — measured. 0 disables it.
    vision_max_image_edge: int = 2560
    # Guardrails for the disk-backed screenshot classifier queue. Stale replay
    # must not block current safety events after upgrades/restarts.
    # Cold qwen3-vl startup on a 12 GB GPU can exceed a minute after a clean
    # install. Keep this above warm latency so first-run safety checks do not
    # spin in repeated Ollama timeouts.
    vision_timeout_seconds: int = 240
    pending_frame_max_age_seconds: int = 600
    pending_replay_max_frames: int = 50

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def setup_token_path(self) -> Path:
        return self.keys_dir / "setup_token"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

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

    @property
    def classifier_mode_resolved(self) -> str:
        aliases = {
            "rules_only": "rules_only",
            "text_llm": "text_llm",
            "vision": "vision",
            "full": "full",
            "text_only": "text_llm",
            "vision_only": "vision",
        }
        configured = (self.classifier_mode or self.classifier_tier).strip().lower()
        return aliases.get(configured, configured)

    @property
    def ocr_language_list(self) -> list[str]:
        return list(dict.fromkeys(part.strip() for part in self.ocr_languages.split(",") if part.strip()))

    def effective_allowed_hosts(self) -> list[str]:
        configured = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        if "*" in configured:
            if self.dev_mode:
                if configured == ["*"]:
                    return ["*"]
                raise ValueError("GUARDIANNODE_ALLOWED_HOSTS cannot combine '*' with explicit hosts")
            raise ValueError("GUARDIANNODE_ALLOWED_HOSTS='*' is only allowed when GUARDIANNODE_DEV_MODE=true")
        hosts = configured or ["127.0.0.1", "localhost", "::1", "testserver"]
        for host in hosts:
            _validate_allowed_host(host)
        if not self.binds_beyond_loopback():
            _validate_allowed_host(self.bind_host)
            hosts.append(self.bind_host)
        return list(dict.fromkeys(hosts))

    def binds_beyond_loopback(self) -> bool:
        host = self.bind_host.strip()
        if not host:
            return True
        try:
            # Any concrete LAN/WAN address is still beyond loopback.  Hostnames
            # are conservatively treated as exposed because they may resolve to
            # a non-loopback interface at runtime.
            return not ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host.lower() != "localhost"

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.keys_dir,
            self.evidence_dir,
            self.logs_dir,
            self.backups_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def _validate_allowed_host(host: str) -> None:
    if not host:
        raise ValueError(f"Invalid allowed host: {host!r}")
    parsed_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(parsed_host)
        return
    except ValueError:
        pass
    if any(ch in host for ch in "/:@"):
        raise ValueError(f"Invalid allowed host: {host!r}")
    if _HOSTNAME_RE.fullmatch(host):
        return
    raise ValueError(f"Invalid allowed host: {host!r}")


settings = Settings()
