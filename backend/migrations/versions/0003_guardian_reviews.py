"""Add encrypted Guardian Review previews and assessments.

Revision ID: 0003_guardian_reviews
Revises: 0002_complete_backups
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_guardian_reviews"
down_revision = "0002_complete_backups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "guardian_review_previews" not in tables:
        op.create_table(
            "guardian_review_previews",
            sa.Column("preview_id", sa.String(64), primary_key=True),
            sa.Column("alert_id", sa.String(64), sa.ForeignKey("alerts.alert_id"), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("model_requested", sa.String(128), nullable=False),
            sa.Column("schema_version", sa.String(32), nullable=False),
            sa.Column("prompt_version", sa.String(64), nullable=False),
            sa.Column("payload_digest", sa.String(64), nullable=False),
            sa.Column("incident_fingerprint", sa.String(64), nullable=False),
            sa.Column("payload_enc", sa.LargeBinary(), nullable=False),
            sa.Column("fresh_assessment", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_id", sa.String(64), nullable=True),
        )
        op.create_index("ix_guardian_review_previews_alert_time", "guardian_review_previews", ["alert_id", "created_at"])
        op.create_index("ix_guardian_review_previews_payload_digest", "guardian_review_previews", ["payload_digest"])
        op.create_index("ix_guardian_review_previews_expires_at", "guardian_review_previews", ["expires_at"])
    if "guardian_reviews" not in tables:
        op.create_table(
            "guardian_reviews",
            sa.Column("review_id", sa.String(64), primary_key=True),
            sa.Column("preview_id", sa.String(64), sa.ForeignKey("guardian_review_previews.preview_id"), nullable=False),
            sa.Column("alert_id", sa.String(64), sa.ForeignKey("alerts.alert_id"), nullable=False),
            sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("dedup_key", sa.String(64), nullable=False),
            sa.Column("schema_version", sa.String(32), nullable=False),
            sa.Column("prompt_version", sa.String(64), nullable=False),
            sa.Column("model_requested", sa.String(128), nullable=False),
            sa.Column("model_returned", sa.String(128), nullable=True),
            sa.Column("provider_response_id", sa.String(128), nullable=True),
            sa.Column("assessment_enc", sa.LargeBinary(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ux_guardian_reviews_dedup_key", "guardian_reviews", ["dedup_key"], unique=True)
        op.create_index("ix_guardian_reviews_status_time", "guardian_reviews", ["status", "created_at"])
        op.create_index("ix_guardian_reviews_alert_time", "guardian_reviews", ["alert_id", "created_at"])


def downgrade() -> None:
    raise RuntimeError("Guardian Review records do not support destructive downgrade")
