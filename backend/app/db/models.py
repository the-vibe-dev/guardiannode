"""SQLAlchemy ORM models for GuardianNode."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    recovery_hash: Mapped[str] = mapped_column(String(256))  # Argon2 hash of recovery code
    role: Mapped[str] = mapped_column(String(32), default="admin")  # admin | parent | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(256))
    platform: Mapped[str] = mapped_column(String(32), default="unknown")
    agent_version: Mapped[str] = mapped_column(String(32), default="0.0.0")
    token_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paired: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="offline")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Child profile this device belongs to. The parent assigns it in the
    # dashboard; the backend tags frames from this device with it so custom
    # watch phrases / age group apply without touching the child's PC.
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ChildProfile(Base):
    __tablename__ = "child_profiles"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    age_group: Mapped[str] = mapped_column(String(16))  # under_10 | 10_13 | 14_17
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Parent-configured phrases to flag (child's real name, address, school,
    # nicknames, anything the parent wants matched in OCR'd text). Severity high.
    custom_watch_phrases: Mapped[list] = mapped_column(JSON, default=list)
    # Privacy / alert-threshold / capture policy (see services/profile_policy.py).
    # Empty = age-group defaults are used.
    alert_policy: Mapped[dict] = mapped_column(JSON, default=dict)


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey("child_profiles.profile_id"))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_device_time", "device_id", "timestamp"),
        Index("ix_events_profile_time", "profile_id", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"))
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32))
    app_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    window_title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    url: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Encrypted blob for redacted text (nonce + ciphertext + tag, base64)
    redacted_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(32), default="visible_text")
    screenshot_blob_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_blob_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    key_version: Mapped[int] = mapped_column(Integer, default=1)


class RiskResult(Base):
    __tablename__ = "risk_results"
    __table_args__ = (Index("ix_risk_level_time", "risk_level", "created_at"),)

    risk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.event_id"))
    risk_level: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(String(32), default="none")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rules_triggered: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0)
    false_positive_notes: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_status_severity", "status", "severity"),)

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    risk_id: Mapped[str] = mapped_column(String(64), ForeignKey("risk_results.risk_id"))
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Repeat aggregation: identical open findings fold into one alert.
    dedup_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    repeat_count: Mapped[int] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceBlob(Base):
    __tablename__ = "evidence_blobs"

    blob_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(64), default="application/octet-stream")
    encrypted_path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256_plain: Mapped[str] = mapped_column(String(64), default="")
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_actor_time", "actor", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128))  # user_id, device_id, "system"
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ModelConfigRow(Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    runtime: Mapped[str] = mapped_column(String(32), default="ollama")
    role: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(String(256))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    result: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChildRequest(Base):
    __tablename__ = "child_requests"
    __table_args__ = (Index("ix_child_requests_status_time", "status", "created_at"),)

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_type: Mapped[str] = mapped_column(String(32))
    target: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
