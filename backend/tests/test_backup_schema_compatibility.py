"""Backups must restore every shipped migration, and reject future schemas."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app import settings as settings_mod
from app.db.maintenance import (
    DatabaseMaintenanceError,
    backup_database,
    backup_manifest_path,
    database_schema_revision,
    restore_database,
)
from app.db.migrations import schema_revisions, upgrade_schema
from app.db.models import Setting
from app.db.session import get_engine, get_sessionmaker


def _current_database():
    engine = get_engine()
    upgrade_schema(engine)
    with get_sessionmaker()() as db:
        db.add(Setting(key="restore_test_marker", value="synthetic family setting"))
        db.commit()
    return settings_mod.settings.data_dir / "guardiannode.db", schema_revisions(engine)[1]


def test_current_head_database_backup_restores_with_existing_data(tmp_path):
    source, head = _current_database()
    backup = backup_database(tmp_path / "head-backup.sqlite3", source=source)
    restored = restore_database(backup, destination=tmp_path / "restored.sqlite3")

    assert database_schema_revision(restored) == head
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT value FROM settings WHERE key='restore_test_marker'").fetchone() == (
            "synthetic family setting",
        )
        assert "delivered_channels" in {row[1] for row in db.execute("PRAGMA table_info(notification_jobs)")}


@pytest.mark.parametrize("keep_manifest", [True, False])
def test_future_embedded_schema_cannot_be_restored_even_without_manifest(tmp_path, keep_manifest):
    source, _head = _current_database()
    with sqlite3.connect(source) as db:
        db.execute("UPDATE alembic_version SET version_num='9999_unknown_future'")
    backup = backup_database(tmp_path / "future-backup.sqlite3", source=source)
    if not keep_manifest:
        backup_manifest_path(backup).unlink()

    destination = tmp_path / "must-not-be-created.sqlite3"
    with pytest.raises(DatabaseMaintenanceError, match="schema revision"):
        restore_database(backup, destination=destination)
    assert not destination.exists()


@pytest.mark.parametrize("declared", ["9999_unknown_future", "0001_beta_baseline", ["invalid-type"]])
def test_backup_rejects_tampered_declared_schema(tmp_path, declared):
    source, _head = _current_database()
    backup = backup_database(tmp_path / "tampered-manifest.sqlite3", source=source)
    manifest_path = backup_manifest_path(backup)
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_revision"] = declared
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(DatabaseMaintenanceError, match="schema revision"):
        restore_database(backup, destination=tmp_path / "must-not-be-created.sqlite3")


def test_backup_rejects_non_object_manifest(tmp_path):
    source, _head = _current_database()
    backup = backup_database(tmp_path / "invalid-manifest.sqlite3", source=source)
    backup_manifest_path(backup).write_text("[]")
    with pytest.raises(DatabaseMaintenanceError, match="manifest"):
        restore_database(backup, destination=tmp_path / "must-not-be-created.sqlite3")
