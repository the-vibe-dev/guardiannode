from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

SCHEMA_FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


def _configure_database(monkeypatch, root: Path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(root))
    from app import settings as settings_mod
    from app.db import session as session_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.ensure_dirs()
    session_mod._engine = None
    session_mod._SessionLocal = None
    return root / "guardiannode.db"


def test_baseline_revision_is_immutable_and_does_not_import_models() -> None:
    revision = Path(__file__).parents[1] / "migrations" / "versions" / "0001_beta_baseline.py"
    text = revision.read_text(encoding="utf-8")
    assert "app.db.models" not in text
    assert "metadata.create_all" not in text


def test_empty_database_migrates_to_snapshotted_schema(monkeypatch, tmp_path: Path):
    _configure_database(monkeypatch, tmp_path)
    from app.db.migrations import schema_revisions, upgrade_schema
    from app.db.session import get_engine

    engine = get_engine()
    upgrade_schema(engine)
    fixture = json.loads(
        (SCHEMA_FIXTURES / "0001_beta_baseline.json").read_text(encoding="utf-8")
    )
    assert sorted(inspect(engine).get_table_names()) == fixture["tables"]
    assert schema_revisions(engine)[0] == fixture["revision"]


def test_migration_upgrades_alpha_schema_and_creates_backup(monkeypatch, tmp_path: Path):
    db_path = _configure_database(monkeypatch, tmp_path)
    with sqlite3.connect(db_path) as connection:
        connection.executescript((SCHEMA_FIXTURES / "alpha.sql").read_text(encoding="utf-8"))

    from app.db.migrations import schema_revisions, upgrade_schema
    from app.db.session import get_engine

    engine = get_engine()
    result = upgrade_schema(engine)
    current, head = schema_revisions(engine)
    assert current == head == "0001_beta_baseline"
    assert result["backup"] is not None
    assert Path(result["backup"]).is_file()
    assert "session_revoked_at" in {col["name"] for col in inspect(engine).get_columns("users")}
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT display_name FROM users").scalar_one() == "Existing Parent"


def test_interrupted_unstamped_migration_recovers_without_losing_evidence(monkeypatch, tmp_path: Path):
    _configure_database(monkeypatch, tmp_path)
    from app.db.migrations import upgrade_schema
    from app.db.session import get_engine

    engine = get_engine()
    upgrade_schema(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM alembic_version")
        connection.exec_driver_sql(
            "INSERT INTO evidence_blobs "
            "(blob_id, kind, mime_type, encrypted_path, size_bytes, sha256_plain, "
            "key_version, created_at, event_id) VALUES "
            "('blob-1', 'screenshot', 'image/png', 'evidence/blob-1.enc', 42, 'abc', 1, "
            "'2026-01-01', NULL)"
        )
    result = upgrade_schema(engine)
    assert result["current_revision"] == "0001_beta_baseline"
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT encrypted_path FROM evidence_blobs WHERE blob_id='blob-1'"
        ).scalar_one() == "evidence/blob-1.enc"


def test_readiness_checks_workers_schema_storage_and_encryption(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUARDIANNODE_READINESS_MIN_FREE_BYTES", "1")
    monkeypatch.setenv("GUARDIANNODE_DATABASE_BACKUP_INTERVAL_SECONDS", "86400")
    monkeypatch.setenv("GUARDIANNODE_CLASSIFIER_MODE", "rules_only")
    from app import settings as settings_mod
    from app.db import session as session_mod
    from app.services import worker_supervisor

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    session_mod._engine = None
    session_mod._SessionLocal = None
    worker_supervisor.reset_for_tests()

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/health/ready")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ready"
        assert all(item["ok"] for item in body["checks"].values())


def test_scheduled_backup_is_restorable_and_prunes_old_generations(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod
    from app.db import session as session_mod
    from app.db.maintenance import backup_database, integrity_check, restore_database
    from app.db.models import Base
    from app.db.session import get_engine
    from app.workers import backup_worker

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.database_backup_keep = 1
    settings_mod.settings.ensure_dirs()
    session_mod._engine = None
    session_mod._SessionLocal = None
    Base.metadata.create_all(get_engine())
    source = tmp_path / "guardiannode.db"
    old = settings_mod.settings.backups_dir / "scheduled-20000101T000000Z.sqlite3"
    backup_database(old, source=source)

    scheduled = backup_worker.run_once()
    assert scheduled is not None and scheduled.is_file()
    assert list(settings_mod.settings.backups_dir.glob("scheduled-*.sqlite3")) == [scheduled]
    assert not list(settings_mod.settings.backups_dir.glob(".*.partial-wal"))
    assert not list(settings_mod.settings.backups_dir.glob(".*.partial-shm"))

    restored = tmp_path / "restore-drill.sqlite3"
    restore_database(scheduled, destination=restored)
    assert integrity_check(restored).ok
