"""Invalidate alpha device credentials for the family-beta security boundary.

Revision ID: 0006_beta_security_break
Revises: 0005_guardian_review_feedback
"""
from __future__ import annotations

from alembic import op

revision = "0006_beta_security_break"
down_revision = "0005_guardian_review_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alpha tokens used password hashing and some releases accepted opaque
    # tokens. There is no safe in-place conversion without knowing the secret.
    # The clean beta break requires an explicit re-pair for every child device.
    op.execute(
        "UPDATE devices SET paired = 0, status = 're_pair_required', token_hash = NULL "
        "WHERE paired = 1 OR token_hash IS NOT NULL"
    )


def downgrade() -> None:
    raise RuntimeError("invalidated alpha device credentials cannot be restored")
