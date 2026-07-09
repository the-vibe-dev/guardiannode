"""Establish the beta schema baseline for fresh and upgraded alpha databases."""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

from app.db.models import Base

revision = "0001_beta_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns(table)}
    if column not in columns:
        bind.execute(text(ddl))


def upgrade() -> None:
    bind = op.get_bind()
    # create_all handles a fresh beta install.  The guarded ALTER statements
    # below upgrade every public alpha schema without destructive rebuilds.
    Base.metadata.create_all(bind=bind)
    tables = set(inspect(bind).get_table_names())
    if "child_profiles" in tables:
        _add_column_if_missing(
            "child_profiles",
            "custom_watch_phrases",
            "ALTER TABLE child_profiles ADD COLUMN custom_watch_phrases TEXT DEFAULT '[]'",
        )
        _add_column_if_missing(
            "child_profiles",
            "alert_policy",
            "ALTER TABLE child_profiles ADD COLUMN alert_policy TEXT DEFAULT '{}'",
        )
    if "alerts" in tables:
        _add_column_if_missing(
            "alerts", "dedup_key", "ALTER TABLE alerts ADD COLUMN dedup_key VARCHAR(64)"
        )
        _add_column_if_missing(
            "alerts",
            "repeat_count",
            "ALTER TABLE alerts ADD COLUMN repeat_count INTEGER DEFAULT 1",
        )
        _add_column_if_missing(
            "alerts", "last_seen_at", "ALTER TABLE alerts ADD COLUMN last_seen_at DATETIME"
        )
    if "devices" in tables:
        _add_column_if_missing(
            "devices", "profile_id", "ALTER TABLE devices ADD COLUMN profile_id VARCHAR(64)"
        )
    if "users" in tables:
        _add_column_if_missing(
            "users",
            "session_revoked_at",
            "ALTER TABLE users ADD COLUMN session_revoked_at DATETIME",
        )
        bind.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin "
                "ON users(role) WHERE role = 'admin'"
            )
        )
    if "risk_results" in tables:
        _add_column_if_missing(
            "risk_results",
            "classifier_status",
            "ALTER TABLE risk_results ADD COLUMN classifier_status VARCHAR(48) DEFAULT 'ok'",
        )


def downgrade() -> None:
    # This baseline intentionally has no destructive downgrade. Application
    # rollback remains safe because every alpha-era addition is nullable or has
    # a backward-compatible default.
    return None
