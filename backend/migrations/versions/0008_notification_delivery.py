"""Persist per-channel notification outcomes and bounded digest retries.

Revision ID: 0008_notification_delivery
Revises: 0007_family_beta_workflows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_notification_delivery"
down_revision = "0007_family_beta_workflows"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column("notification_jobs", sa.Column(
        "delivered_channels", sa.JSON(), nullable=False, server_default="[]",
    ))
    _add_column("digest_runs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    _add_column("digest_runs", sa.Column(
        "delivered_channels", sa.JSON(), nullable=False, server_default="[]",
    ))
    _add_column("digest_runs", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("digest_runs", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("notification delivery state requires restoring a pre-upgrade backup to downgrade")
