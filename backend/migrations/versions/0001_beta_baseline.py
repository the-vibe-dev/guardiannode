"""Establish the immutable beta schema baseline.

This revision deliberately contains the complete schema instead of importing
ORM metadata. Historical migrations must produce the same result even after
application models change.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op

revision = "0001_beta_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _create(name: str, *columns: sa.Column, **kwargs) -> bool:
    if name in _tables():
        return False
    op.create_table(name, *columns, **kwargs)
    return True


def _index(name: str, table: str, columns: list[str], *, unique: bool = False, sqlite_where=None) -> None:
    indexes = {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique, sqlite_where=sqlite_where)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _create(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("recovery_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _add_column_if_missing("users", sa.Column("session_revoked_at", sa.DateTime(timezone=True)))
    _index(
        "ux_users_single_admin", "users", ["role"], unique=True,
        sqlite_where=text("role = 'admin'"),
    )

    _create(
        "devices",
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("hostname", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(256), nullable=True),
        sa.Column("paired", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("device_id"),
    )
    _add_column_if_missing("devices", sa.Column("profile_id", sa.String(64)))

    _create(
        "child_profiles",
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("age_group", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("custom_watch_phrases", sa.JSON(), nullable=False),
        sa.Column("alert_policy", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    _add_column_if_missing(
        "child_profiles", sa.Column("custom_watch_phrases", sa.JSON(), server_default="[]")
    )
    _add_column_if_missing(
        "child_profiles", sa.Column("alert_policy", sa.JSON(), server_default="{}")
    )

    _create(
        "policies",
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["child_profiles.profile_id"]),
        sa.PrimaryKeyConstraint("policy_id"),
    )
    _create(
        "screenshot_upload_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("upload_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index(
        "ux_screenshot_upload_device_key", "screenshot_upload_receipts",
        ["device_id", "idempotency_key"], unique=True,
    )
    _create(
        "events",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("app_name", sa.String(256), nullable=True),
        sa.Column("window_title", sa.String(1024), nullable=True),
        sa.Column("url", sa.String(4096), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redacted_text_enc", sa.LargeBinary(), nullable=True),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("screenshot_blob_id", sa.String(64), nullable=True),
        sa.Column("image_blob_id", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    _index("ix_events_device_time", "events", ["device_id", "timestamp"])
    _index("ix_events_profile_time", "events", ["profile_id", "timestamp"])
    _index("ix_events_timestamp", "events", ["timestamp"])
    _create(
        "risk_results",
        sa.Column("risk_id", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("rules_triggered", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("false_positive_notes", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("rules_version", sa.String(32), nullable=True),
        sa.Column("classifier_status", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.event_id"]),
        sa.PrimaryKeyConstraint("risk_id"),
    )
    _add_column_if_missing(
        "risk_results", sa.Column("classifier_status", sa.String(48), server_default="ok")
    )
    _index("ix_risk_level_time", "risk_results", ["risk_level", "created_at"])
    _create(
        "alerts",
        sa.Column("alert_id", sa.String(64), nullable=False),
        sa.Column("risk_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("profile_id", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_taken", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.String(64), nullable=True),
        sa.Column("repeat_count", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["risk_id"], ["risk_results.risk_id"]),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    _add_column_if_missing("alerts", sa.Column("dedup_key", sa.String(64)))
    _add_column_if_missing("alerts", sa.Column("repeat_count", sa.Integer(), server_default="1"))
    _add_column_if_missing("alerts", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    _index("ix_alerts_status_severity", "alerts", ["status", "severity"])
    _index("ix_alerts_created_at", "alerts", ["created_at"])
    _index("ix_alerts_dedup_key", "alerts", ["dedup_key"])
    _create(
        "evidence_blobs",
        sa.Column("blob_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("encrypted_path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_plain", sa.String(64), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("blob_id"),
    )
    _create(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(256), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_audit_actor_time", "audit_logs", ["actor", "created_at"])
    _index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    _create(
        "model_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create(
        "pairing_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code_hash", sa.String(256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create(
        "notification_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=False),
        sa.Column("immediate", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.alert_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_notification_jobs_status_due", "notification_jobs", ["status", "next_attempt_at"])
    _create(
        "child_requests",
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("profile_id", sa.String(64), nullable=True),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("target", sa.String(1024), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("request_id"),
    )
    _index("ix_child_requests_status_time", "child_requests", ["status", "created_at"])
    _create(
        "settings",
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    raise RuntimeError("The beta baseline does not support destructive downgrade")
