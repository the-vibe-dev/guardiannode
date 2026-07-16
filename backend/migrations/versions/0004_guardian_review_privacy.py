"""Add Guardian Review privacy and deletion metadata.

Revision ID: 0004_guardian_review_privacy
Revises: 0003_guardian_reviews
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0004_guardian_review_privacy"
down_revision = "0003_guardian_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    preview_columns = {column["name"] for column in inspector.get_columns("guardian_review_previews")}
    if "redaction_version" not in preview_columns:
        op.add_column(
            "guardian_review_previews",
            sa.Column(
                "redaction_version",
                sa.String(64),
                nullable=False,
                server_default="guardian-review-redaction-v1",
            ),
        )
    if "information_categories" not in preview_columns:
        op.add_column(
            "guardian_review_previews",
            sa.Column("information_categories", sa.JSON(), nullable=False, server_default=json.dumps([])),
        )
    with op.batch_alter_table("guardian_review_previews") as batch:
        batch.alter_column("payload_enc", existing_type=sa.LargeBinary(), nullable=True)

    inspector = sa.inspect(op.get_bind())
    review_columns = {column["name"] for column in inspector.get_columns("guardian_reviews")}
    if "redaction_version" not in review_columns:
        op.add_column(
            "guardian_reviews",
            sa.Column(
                "redaction_version",
                sa.String(64),
                nullable=False,
                server_default="guardian-review-redaction-v1",
            ),
        )
    if "deleted_at" not in review_columns:
        op.add_column(
            "guardian_reviews",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    raise RuntimeError("Guardian Review privacy records do not support destructive downgrade")
