"""Evidence export includes the actual encrypted blob files."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.services import pipeline_metrics, rate_limit


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    pipeline_metrics.reset_for_tests()
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def test_export_contains_encrypted_evidence_blobs(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
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

    # Seed one event + evidence blob with a real encrypted file on disk.
    from app.db.session import get_sessionmaker
    from app.db.models import Event, EvidenceBlob
    from app.services import encryption
    from app.settings import settings
    from datetime import datetime, timezone

    blob_dir = settings.evidence_dir / "ab"
    blob_path = blob_dir / "blob1.enc"
    encryption.encrypt_blob_to_disk(b"fake-jpeg-bytes", blob_path, aad=b"blob1")

    s = get_sessionmaker()()
    s.add(Event(event_id="e1", device_id="d1", source_type="image",
                timestamp=datetime.now(timezone.utc), screenshot_blob_id="blob1"))
    s.add(EvidenceBlob(blob_id="blob1", kind="screenshot",
                       encrypted_path=str(blob_path), size_bytes=15, event_id="e1"))
    s.commit()
    s.close()

    r = client.post("/api/storage/export")
    assert r.status_code == 200
    assert "path" not in r.json()
    export_id = r.json()["export_id"]
    export_path = settings.data_dir / "exports" / f"{export_id}.gnexport"
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

    # Decrypt the outer .gnexport and verify package contents.
    payload = encryption.decrypt_stream_file_from_disk(
        export_path, aad=export_id.encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "alerts.jsonl", "events.jsonl",
                "risk_results.jsonl", "audit_logs.jsonl", "evidence_manifest.json"} <= names
        assert "evidence/blob1.enc" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["includes_evidence_blobs"] is True
        assert manifest["evidence_blob_count"] == 1
        evidence_manifest = json.loads(zf.read("evidence_manifest.json"))
        assert evidence_manifest[0]["blob_id"] == "blob1"
        assert "encrypted_path" not in evidence_manifest[0]
        # The embedded blob is the exact ciphertext from disk and still decrypts.
        inner = zf.read("evidence/blob1.enc")
        assert encryption.decrypt_bytes(inner, aad=b"blob1") == b"fake-jpeg-bytes"

    deleted = client.delete(f"/api/storage/exports/{export_id}")
    assert deleted.status_code == 200
    assert not export_path.exists()
    assert client.get("/api/storage/exports").json() == []

    audit = client.get("/api/audit").json()
    export_rows = [row for row in audit if row["action"].startswith("storage.export")]
    assert any(row["action"] == "storage.export.download" for row in export_rows)
    assert all("path" not in (row.get("details") or {}) for row in export_rows)
