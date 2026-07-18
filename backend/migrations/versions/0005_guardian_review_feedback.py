"""Add Guardian Review feedback and content-free model usage metadata.

Revision ID: 0005_guardian_review_feedback
Revises: 0004_guardian_review_privacy
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_guardian_review_feedback"
down_revision = "0004_guardian_review_privacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    review_columns = {column["name"] for column in inspector.get_columns("guardian_reviews")}
    for name in (
        "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"
    ):
        if name not in review_columns:
            op.add_column("guardian_reviews", sa.Column(name, sa.Integer(), nullable=True))

    if "guardian_review_feedback" not in set(inspector.get_table_names()):
        op.create_table(
            "guardian_review_feedback",
            sa.Column("feedback_id", sa.String(64), primary_key=True),
            sa.Column("review_id", sa.String(64), sa.ForeignKey("guardian_reviews.review_id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("labels", sa.JSON(), nullable=False),
            sa.Column("schema_version", sa.String(32), nullable=False),
            sa.Column("prompt_version", sa.String(64), nullable=False),
            sa.Column("redaction_version", sa.String(64), nullable=False),
            sa.Column("model", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ux_guardian_review_feedback_review_user",
            "guardian_review_feedback",
            ["review_id", "user_id"],
            unique=True,
        )


def downgrade() -> None:
    raise RuntimeError("Guardian Review feedback records do not support destructive downgrade")
