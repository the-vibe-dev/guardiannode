"""Add durable deletion, consent, commands, requests, and digest workflows.

Revision ID: 0007_family_beta_workflows
Revises: 0006_beta_security_break
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_family_beta_workflows"
down_revision = "0006_beta_security_break"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column("events", sa.Column("deletion_state", sa.String(32), nullable=False, server_default="active"))
    _add_column("events", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("evidence_blobs", sa.Column("deletion_state", sa.String(32), nullable=False, server_default="active"))
    _add_column("evidence_blobs", sa.Column("delete_attempts", sa.Integer(), nullable=False, server_default="0"))
    _add_column("evidence_blobs", sa.Column("delete_requested_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("evidence_blobs", sa.Column("last_delete_error", sa.Text(), nullable=True))
    _add_column("child_requests", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "consent_records" not in tables:
        op.create_table(
            "consent_records",
            sa.Column("consent_id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("notice_version", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("choices", sa.JSON(), nullable=False),
            sa.Column("supersedes_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_consent_records_user_time", "consent_records", ["user_id", "created_at"])
    if "device_commands" not in tables:
        op.create_table(
            "device_commands",
            sa.Column("command_id", sa.String(64), primary_key=True),
            sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.device_id"), nullable=False),
            sa.Column("alert_id", sa.String(64), nullable=True),
            sa.Column("command_type", sa.String(32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("preview", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", sa.JSON(), nullable=False),
            sa.Column("undo_of", sa.String(64), nullable=True),
        )
        op.create_index(
            "ix_device_commands_device_status_time", "device_commands",
            ["device_id", "status", "created_at"],
        )
        op.create_index("ix_device_commands_alert_time", "device_commands", ["alert_id", "created_at"])
    if "digest_runs" not in tables:
        op.create_table(
            "digest_runs",
            sa.Column("digest_id", sa.String(64), primary_key=True),
            sa.Column("local_date", sa.String(10), nullable=False),
            sa.Column("timezone", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ux_digest_runs_local_day", "digest_runs", ["local_date", "timezone"], unique=True)
        op.create_index("ix_digest_runs_status_time", "digest_runs", ["status", "created_at"])

    op.execute(
        "UPDATE child_requests SET expires_at = datetime(created_at, '+7 days') WHERE expires_at IS NULL"
    )


def downgrade() -> None:
    raise RuntimeError("family beta workflow records do not support destructive downgrade")
