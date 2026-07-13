from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app import settings as settings_mod
from app.archive import crypto
from app.archive.format import (
    ArchiveError,
    create_archive,
    inspect_archive,
    restore_archive,
    verify_archive,
)
from app.db.migrations import upgrade_schema
from app.db.session import configure_sqlite_engine
from app.services import encryption


@pytest.fixture
def archive_instance(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    database = data_dir / "guardiannode.db"
    monkeypatch.setattr(settings_mod.settings, "data_dir", data_dir)
    monkeypatch.setattr(settings_mod.settings, "db_url", f"sqlite:///{database}")
    engine = configure_sqlite_engine(create_engine(f"sqlite:///{database}"))
    upgrade_schema(engine)
    engine.dispose()
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO users (display_name,password_hash,recovery_hash,role,created_at) "
            "VALUES ('Parent','password-hash','recovery-hash','admin','2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO devices (device_id,hostname,platform,agent_version,paired,status,created_at) "
            "VALUES ('device-1','child-pc','windows','1.0',1,'online','2026-01-01T00:00:00Z')"
        )
        encrypted = b"n" * 12 + b"ciphertext" + b"t" * 16
        conn.execute(
            "INSERT INTO events (event_id,device_id,source_type,timestamp,redacted_text_enc,"
            "evidence_type,metadata,received_at,key_version) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "event-1", "device-1", "visible_text", "2026-01-01T00:00:00Z", encrypted,
                "visible_text", "{}", "2026-01-01T00:00:00Z", 1,
            ),
        )
    evidence = data_dir / "evidence" / "aa" / "blob.enc"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"exact-evidence-ciphertext")
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO evidence_blobs (blob_id,kind,mime_type,encrypted_path,size_bytes,"
            "sha256_plain,key_version,created_at,event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "blob", "screenshot", "image/jpeg", str(evidence), 25, "hash", 1,
                "2026-01-01T00:00:00Z", "event-1",
            ),
        )
    encryption._reset_cache()
    yield data_dir, database
    encryption._reset_cache()


def test_passphrase_archive_round_trip_and_restore(archive_instance, tmp_path: Path):
    data_dir, database = archive_instance
    archive = tmp_path / "family.gna"
    result = create_archive(
        archive, data_dir=data_dir, db_url=f"sqlite:///{database}",
        passphrase="correct horse battery staple",
    )
    assert result["mode"] == "portable"
    assert inspect_archive(archive)["format"] == "guardiannode-archive-v1"
    verified = verify_archive(archive, passphrase="correct horse battery staple")
    assert verified["manifest"]["record_counts"]["events"] == 1
    assert verified["manifest"]["evidence"]["file_count"] == 1

    target = tmp_path / "restored"
    restored = restore_archive(
        archive, target, passphrase="correct horse battery staple"
    )
    assert restored["ok"] is True
    assert (target / "evidence" / "aa" / "blob.enc").read_bytes() == b"exact-evidence-ciphertext"
    with sqlite3.connect(target / "guardiannode.db") as conn:
        row = conn.execute(
            "SELECT redacted_text_enc FROM events WHERE event_id='event-1'"
        ).fetchone()
        evidence_path = conn.execute(
            "SELECT encrypted_path FROM evidence_blobs WHERE blob_id='blob'"
        ).fetchone()[0]
    assert row[0] == b"n" * 12 + b"ciphertext" + b"t" * 16
    assert evidence_path == "aa/blob.enc"
    assert (target / "keys" / "master.key").stat().st_size == 32


def test_recipient_archive_and_wrong_key_fail(archive_instance, tmp_path: Path):
    data_dir, database = archive_instance
    private_path = tmp_path / "recovery.pem"
    public_path = tmp_path / "recovery.pub.pem"
    crypto.generate_recipient_key(private_path, public_path)
    archive = tmp_path / "recipient.gna"
    create_archive(
        archive, data_dir=data_dir, db_url=f"sqlite:///{database}",
        recipient_key=crypto.load_public_key(public_path),
    )
    assert verify_archive(archive, private_key=crypto.load_private_key(private_path))["ok"]

    wrong_private = tmp_path / "wrong.pem"
    wrong_public = tmp_path / "wrong.pub.pem"
    crypto.generate_recipient_key(wrong_private, wrong_public)
    with pytest.raises(ArchiveError, match="unable to unlock"):
        verify_archive(archive, private_key=crypto.load_private_key(wrong_private))


def test_altered_archive_fails_without_partial_plaintext(archive_instance, tmp_path: Path):
    data_dir, database = archive_instance
    archive = tmp_path / "family.gna"
    create_archive(
        archive, data_dir=data_dir, db_url=f"sqlite:///{database}",
        passphrase="correct horse battery staple",
    )
    altered = bytearray(archive.read_bytes())
    altered[-12] ^= 1
    archive.write_bytes(altered)
    with pytest.raises(ArchiveError, match="authentication failed"):
        verify_archive(archive, passphrase="correct horse battery staple")
    assert not list(tmp_path.glob("*.partial"))


def test_restore_requires_empty_target(archive_instance, tmp_path: Path):
    data_dir, database = archive_instance
    archive = tmp_path / "family.gna"
    create_archive(
        archive, data_dir=data_dir, db_url=f"sqlite:///{database}",
        passphrase="correct horse battery staple",
    )
    target = tmp_path / "target"
    target.mkdir()
    (target / "existing").write_text("keep")
    with pytest.raises(ArchiveError, match="empty directory"):
        restore_archive(archive, target, passphrase="correct horse battery staple")
    assert (target / "existing").read_text() == "keep"


def test_missing_database_evidence_fails_closed(archive_instance, tmp_path: Path):
    data_dir, database = archive_instance
    (data_dir / "evidence" / "aa" / "blob.enc").unlink()
    with pytest.raises(ArchiveError, match="database-referenced evidence is missing"):
        create_archive(
            tmp_path / "family.gna", data_dir=data_dir,
            db_url=f"sqlite:///{database}", passphrase="correct horse battery staple",
        )
