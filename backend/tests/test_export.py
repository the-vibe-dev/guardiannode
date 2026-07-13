"""Evidence export includes the actual encrypted blob files."""
from __future__ import annotations

from datetime import UTC

import pytest
from fastapi.testclient import TestClient

from app.services import pipeline_metrics, rate_limit


def _client(monkeypatch, tmp_path, *, raise_server_exceptions: bool = True) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    pipeline_metrics.reset_for_tests()
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app

    Base.metadata.create_all(bind=get_engine())
    return TestClient(
        create_app(),
        client=("127.0.0.1", 50000),
        raise_server_exceptions=raise_server_exceptions,
    )


def _login(client: TestClient) -> None:
    from app.services.setup_token import ensure_setup_token

    setup_token = ensure_setup_token()
    r = client.post(
        "/api/auth/setup",
        json={
            "display_name": "P",
            "password": "correct-horse-battery",
            "recovery_code": "a b c d",
            "setup_token": setup_token,
        },
    )
    assert r.status_code == 200
    client.headers.update({"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]})


def _export_plaintext_zips(root) -> list:
    exports_dir = root / "exports"
    if not exports_dir.exists():
        return []
    return list(exports_dir.rglob("*.zip"))


def test_export_contains_encrypted_evidence_blobs(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _login(client)

    # Seed one event + evidence blob with a real encrypted file on disk.
    from datetime import datetime

    from app.db.models import Device, Event, EvidenceBlob
    from app.db.session import get_sessionmaker
    from app.services import encryption
    from app.settings import settings

    blob_dir = settings.evidence_dir / "ab"
    blob_path = blob_dir / "blob1.enc"
    encryption.encrypt_blob_to_disk(b"fake-jpeg-bytes", blob_path, aad=b"blob1")
    s = get_sessionmaker()()
    s.add(Device(device_id="d1", hostname="kid-pc", paired=True))
    s.flush()
    s.add(Event(event_id="e1", device_id="d1", source_type="image",
                timestamp=datetime.now(UTC), screenshot_blob_id="blob1"))
    s.add(EvidenceBlob(blob_id="blob1", kind="screenshot",
                       encrypted_path=str(blob_path), size_bytes=15, event_id="e1"))
    s.commit()
    s.close()

    r = client.post("/api/storage/export")
    assert r.status_code == 200
    assert "path" not in r.json()
    export_id = r.json()["export_id"]
    export_path = settings.data_dir / "exports" / f"{export_id}.gna"
    assert export_path.exists()
    assert r.json()["download_url"] == f"/api/storage/exports/{export_id}/download"

    listed = client.get("/api/storage/exports")
    assert listed.status_code == 200
    assert listed.json()[0]["export_id"] == export_id
    assert "path" not in listed.json()[0]

    downloaded = client.get(r.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store, private"
    assert downloaded.headers["pragma"] == "no-cache"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.content == export_path.read_bytes()

    from app.archive.format import verify_archive

    verified = verify_archive(export_path, master_key=encryption.get_master_key())
    assert verified["manifest"]["format"] == "guardiannode-archive-manifest-v1"
    assert verified["manifest"]["evidence"]["covered"] is True
    assert verified["manifest"]["evidence"]["file_count"] == 1

    deleted = client.delete(f"/api/storage/exports/{export_id}")
    assert deleted.status_code == 200
    assert not export_path.exists()
    assert client.get("/api/storage/exports").json() == []

    audit = client.get("/api/audit").json()
    export_rows = [row for row in audit if row["action"].startswith("storage.export")]
    assert any(row["action"] == "storage.export.download" for row in export_rows)
    assert all("path" not in (row.get("details") or {}) for row in export_rows)


@pytest.mark.parametrize("controlled", [True, False])
def test_failed_export_deletes_plaintext_zip(monkeypatch, tmp_path, controlled):
    client = _client(monkeypatch, tmp_path, raise_server_exceptions=False)
    _login(client)

    from app import settings as settings_mod
    from app.api import storage
    from app.archive.format import ArchiveError

    def fail_archive(*args, **kwargs):
        if controlled:
            raise ArchiveError("simulated validation failure")
        raise RuntimeError("simulated encryption failure")

    monkeypatch.setattr(storage, "create_archive", fail_archive)

    response = client.post("/api/storage/export")
    assert response.status_code == (409 if controlled else 500)
    exports_dir = settings_mod.settings.data_dir / "exports"
    assert _export_plaintext_zips(settings_mod.settings.data_dir) == []
    assert not list(exports_dir.glob("*.partial"))
    assert not (exports_dir / ".ignored-cleanup").exists()


def test_startup_export_cleanup_deletes_stale_plaintext_artifacts(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _login(client)

    from app import settings as settings_mod
    from app.api import storage

    exports_dir = settings_mod.settings.data_dir / "exports"
    tmp_dir = exports_dir / ".tmp"
    tmp_dir.mkdir(parents=True)
    (tmp_dir / "abandoned.zip").write_bytes(b"plaintext zip")
    (exports_dir / "abandoned.tmp").write_bytes(b"tmp")
    (exports_dir / "abandoned.partial").write_bytes(b"partial")

    storage._cleanup_abandoned_exports()

    assert _export_plaintext_zips(settings_mod.settings.data_dir) == []
    assert not (exports_dir / "abandoned.tmp").exists()
    assert not (exports_dir / "abandoned.partial").exists()
    assert not (exports_dir / ".ignored-cleanup").exists()
