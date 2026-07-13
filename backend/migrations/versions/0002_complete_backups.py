"""Add complete backup run history.

Revision ID: 0002_complete_backups
Revises: 0001_beta_baseline
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_complete_backups"
down_revision = "0001_beta_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "backup_runs" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "backup_runs",
        sa.Column("backup_id", sa.String(64), nullable=False),
        sa.Column("backup_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("destination", sa.String(4096), nullable=False),
        sa.Column("archive_path", sa.String(4096), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("archive_sha256", sa.String(64), nullable=True),
        sa.Column("evidence_covered", sa.Boolean(), nullable=False),
        sa.Column("recoverable_key", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restore_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("backup_id"),
    )
    op.create_index("ix_backup_runs_started_at", "backup_runs", ["started_at"])


def downgrade() -> None:
    raise RuntimeError("Complete backup history does not support destructive downgrade")
