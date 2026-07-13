from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db.maintenance import (
    backup_database,
    backup_manifest_path,
    integrity_check,
    restore_database,
    sqlite_path_from_url,
)
from app.db.models import Event


def test_sqlite_foreign_keys_enabled_for_sessions(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    db_session.add(
        Event(
            event_id="event-with-missing-device",
            device_id="missing-device",
            source_type="browser",
            timestamp=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def _sqlite_file(path):
    engine = create_engine(f"sqlite:///{path}", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO items (name) VALUES ('alpha')"))
    engine.dispose()


def _item_names(path):
    engine = create_engine(f"sqlite:///{path}", future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT name FROM items ORDER BY id")).fetchall()
    engine.dispose()
    return [row[0] for row in rows]


def test_sqlite_path_from_url_rejects_non_file_databases():
    assert sqlite_path_from_url("sqlite:////tmp/guardiannode.db").name == "guardiannode.db"
    with pytest.raises(Exception, match="file-backed"):
        sqlite_path_from_url("sqlite:///:memory:")
    with pytest.raises(Exception, match="SQLite only"):
        sqlite_path_from_url("postgresql://example/db")


def test_integrity_backup_and_restore_sqlite_file(tmp_path):
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"
    live = tmp_path / "live.sqlite"
    _sqlite_file(source)
    _sqlite_file(live)

    result = integrity_check(source)
    assert result.ok
    assert result.messages == ["ok"]

    backup_path = backup_database(destination, source=source)
    assert backup_path == destination
    assert destination.is_file()
    manifest = json.loads(backup_manifest_path(destination).read_text(encoding="utf-8"))
    assert manifest["format"] == "guardiannode-sqlite-backup-v1"
    assert manifest["schema_revision"] is None
    assert _item_names(destination) == ["alpha"]

    restored_path = restore_database(destination, destination=live)
    assert restored_path == live
    assert _item_names(live) == ["alpha"]
    retained = list((tmp_path / "backups").glob("pre-restore-*-live.sqlite"))
    assert len(retained) == 1
    assert _item_names(retained[0]) == ["alpha"]


def test_restore_rejects_backup_that_no_longer_matches_manifest(tmp_path):
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    _sqlite_file(source)
    backup_database(backup, source=source)
    with backup.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(Exception, match="manifest checksum"):
        restore_database(backup, destination=tmp_path / "live.sqlite")


def test_backup_refuses_to_overwrite_without_flag(tmp_path):
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"
    _sqlite_file(source)
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(Exception, match="already exists"):
        backup_database(destination, source=source)
