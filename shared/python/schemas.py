"""Pydantic models shared across backend, agent, and dashboard.

These mirror the JSON Schema files in shared/schemas/. Pydantic enforces the
same constraints in Python; the JSON Schema files exist for any non-Python
consumer (TypeScript, docs, etc.).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    OCR = "ocr"
    BROWSER = "browser"
    CLIPBOARD = "clipboard"
    FILE = "file"
    ACCESSIBILITY = "accessibility"
    IMAGE = "image"


class EvidenceType(str, Enum):
    VISIBLE_TEXT = "visible_text"
    URL_ONLY = "url_only"
    IMAGE_REF = "image_ref"
    CLIPBOARD_TEXT = "clipboard_text"
    FILE_REF = "file_ref"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def numeric(self) -> int:
        return {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class RiskCategory(str, Enum):
    GROOMING = "grooming"
    OFF_PLATFORM_CONTACT = "off_platform_contact"
    SECRECY_REQUEST = "secrecy_request"
    BULLYING = "bullying"
    HARASSMENT = "harassment"
    SELF_HARM = "self_harm"
    SEXUAL_CONTENT = "sexual_content"
    NUDITY = "nudity"
    GORE = "gore"
    WEAPONS = "weapons"
    DRUGS = "drugs"
    HATE_SYMBOL = "hate_symbol"
    PRIVATE_INFO_REQUEST = "private_info_request"
    PRIVATE_INFO_VISIBLE = "private_info_visible"
    SCAM = "scam"
    PHISHING = "phishing"
    PHISHING_SCREENSHOT = "phishing_screenshot"
    THREAT = "threat"
    DANGEROUS_CHALLENGE = "dangerous_challenge"
    VIOLENCE = "violence"
    QR_CODE = "qr_code"


class RecommendedAction(str, Enum):
    NONE = "none"
    LOG = "log"
    ALERT_PARENT = "alert_parent"
    PAUSE_APP = "pause_app"
    BLOCK_APP = "block_app"
    EMERGENCY_REVIEW = "emergency_review"


class AlertStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    FALSE_POSITIVE = "false_positive"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    PAUSED = "paused"
    DISABLED = "disabled"


class Platform(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class AgeGroup(str, Enum):
    UNDER_10 = "under_10"
    TEN_TO_THIRTEEN = "10_13"
    FOURTEEN_TO_SEVENTEEN = "14_17"


class EvidenceKind(str, Enum):
    SCREENSHOT = "screenshot"
    IMAGE = "image"
    CLIPBOARD_IMAGE = "clipboard_image"
    FILE_EXCERPT = "file_excerpt"


class ModelRole(str, Enum):
    TEXT_SAFETY_CLASSIFIER = "text_safety_classifier"
    IMAGE_SAFETY_CLASSIFIER = "image_safety_classifier"


class EnforcementAction(str, Enum):
    LOG_ONLY = "log_only"
    NOTIFY_PARENT = "notify_parent"
    NOTIFY_PARENT_DIGEST = "notify_parent_digest"
    PAUSE_APP = "pause_app"
    KILL_APP = "kill_app"
    BLOCK_DOMAIN = "block_domain"
    PROMPT_CHILD = "prompt_child"


# ----- Models ----------------------------------------------------------------


class Event(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    event_id: str
    device_id: str = Field(max_length=128)
    profile_id: str | None = Field(default=None, max_length=128)
    source_type: SourceType
    app_name: str | None = Field(default=None, max_length=256)
    window_title: str | None = Field(default=None, max_length=1024)
    url: str | None = Field(default=None, max_length=4096)
    timestamp: datetime
    redacted_text: str | None = Field(default=None, max_length=16384)
    evidence_type: EvidenceType = EvidenceType.VISIBLE_TEXT
    screenshot_blob_id: str | None = None
    image_blob_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    risk_id: str
    event_id: str
    risk_level: RiskLevel
    score: int = Field(ge=0, le=100)
    categories: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=2048)
    evidence: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction = RecommendedAction.NONE
    model: str | None = None
    rules_triggered: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    false_positive_notes: str = Field(default="", max_length=2048)
    prompt_version: str | None = None
    rules_version: str | None = None


class Alert(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    alert_id: str
    risk_id: str
    device_id: str | None = None
    profile_id: str | None = None
    severity: RiskLevel
    status: AlertStatus = AlertStatus.OPEN
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    action_taken: str | None = None
    notes: str | None = Field(default=None, max_length=4096)


class Device(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    device_id: str
    hostname: str = Field(max_length=256)
    platform: Platform = Platform.UNKNOWN
    agent_version: str = "0.0.0"
    created_at: datetime
    last_seen: datetime | None = None
    paired: bool = False
    profile_ids: list[str] = Field(default_factory=list)
    status: DeviceStatus = DeviceStatus.OFFLINE


class ChildProfile(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    profile_id: str
    display_name: str = Field(max_length=128)
    age_group: AgeGroup
    created_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2048)
    custom_watch_phrases: list[str] = Field(default_factory=list, max_length=200)


class SeverityThresholds(BaseModel):
    alert_at: RiskLevel = RiskLevel.MEDIUM
    notify_at: RiskLevel = RiskLevel.HIGH


class EnforcementMap(BaseModel):
    on_critical: list[EnforcementAction] = Field(
        default_factory=lambda: [EnforcementAction.NOTIFY_PARENT]
    )
    on_high: list[EnforcementAction] = Field(
        default_factory=lambda: [EnforcementAction.NOTIFY_PARENT]
    )
    on_medium: list[EnforcementAction] = Field(
        default_factory=lambda: [EnforcementAction.NOTIFY_PARENT_DIGEST]
    )
    on_low: list[EnforcementAction] = Field(
        default_factory=lambda: [EnforcementAction.LOG_ONLY]
    )


class RetentionDays(BaseModel):
    critical: int = 90
    high: int = 90
    medium: int = 30
    low: int = 1


class Policy(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    policy_id: str
    profile_id: str
    monitored_apps: list[str] = Field(default_factory=list)
    monitored_domains: list[str] = Field(default_factory=list)
    ocr_cadence_seconds: int = Field(default=5, ge=1, le=600)
    image_safety_enabled: bool = True
    clipboard_monitoring_enabled: bool = False
    severity_thresholds: SeverityThresholds = Field(default_factory=SeverityThresholds)
    enforcement: EnforcementMap = Field(default_factory=EnforcementMap)
    retention_days: RetentionDays = Field(default_factory=RetentionDays)


class EvidenceBlobMetadata(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    blob_id: str
    kind: EvidenceKind
    mime_type: str = "application/octet-stream"
    encrypted_path: str
    size_bytes: int = Field(ge=0)
    sha256_plain: str = ""
    key_version: int = 1
    created_at: datetime
    event_id: str | None = None


class ModelConfigParams(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = 0.9
    num_ctx: int = 4096
    seed: int | None = None


class ModelConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    name: str
    runtime: str = "ollama"
    role: ModelRole
    params: ModelConfigParams = Field(default_factory=ModelConfigParams)
    active: bool = True
