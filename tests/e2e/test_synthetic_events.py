from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


CORPUS_PATH = Path(__file__).resolve().parents[1] / "corpus" / "safety_test_cases.json"


def _fresh_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))

    from app import settings as settings_mod
    from app.db import session as session_mod
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app
    from app.services import rate_limit

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    session_mod._engine = None
    session_mod._SessionLocal = None
    rate_limit._clear_all()
    Base.metadata.create_all(bind=get_engine())
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def _setup_parent(client: TestClient, tmp_path: Path) -> None:
    status = client.get("/api/setup/status")
    assert status.status_code == 200
    from app.services.setup_token import ensure_setup_token
    token = ensure_setup_token()
    recovery = client.post("/api/setup/recovery", json={"setup_token": token})
    assert recovery.status_code == 200
    created = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": "correct horse battery",
            "recovery_code": recovery.json()["code"],
            "setup_token": token,
        },
    )
    assert created.status_code == 200
    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    client.headers["X-CSRF-Token"] = csrf.json()["csrf_token"]


def _pair_device(client: TestClient) -> tuple[str, str]:
    issued = client.post("/api/devices/pair/start")
    assert issued.status_code == 200
    paired = client.post(
        "/api/devices/pair/complete",
        json={
            "code": issued.json()["code"],
            "hostname": "synthetic-child-pc",
            "platform": "windows",
            "agent_version": "0.1.0-alpha.1",
        },
    )
    assert paired.status_code == 200
    body = paired.json()
    return body["device_id"], body["device_token"]


def _install_canned_classifier(monkeypatch, corpus: list[dict]) -> None:
    by_text = {case["text"]: case for case in corpus}

    async def fake_classify_text(*, redacted_text: str, **_kwargs):
        case = by_text[redacted_text]
        return {
            "risk_level": case["risk_level"],
            "score": case["score"],
            "categories": case["categories"],
            "summary": case["summary"],
            "evidence": case["evidence"],
            "recommended_action": case["recommended_action"],
            "model": "synthetic-e2e",
            "rules_triggered": [],
            "confidence": 0.99 if case["risk_level"] != "none" else 1.0,
            "false_positive_notes": "",
            "prompt_version": "synthetic-e2e",
            "rules_version": "synthetic-e2e",
            "status": "ok",
        }

    from app.services import classifier

    monkeypatch.setattr(classifier, "classify_text", fake_classify_text)


def test_synthetic_event_lifecycle(monkeypatch, tmp_path):
    corpus = json.loads(CORPUS_PATH.read_text("utf-8"))
    client = _fresh_client(monkeypatch, tmp_path)
    _setup_parent(client, tmp_path)
    _install_canned_classifier(monkeypatch, corpus)

    device_id, device_token = _pair_device(client)
    profile = client.post(
        "/api/profiles",
        json={
            "display_name": "Synthetic Child",
            "age_group": "10_13",
            "custom_watch_phrases": ["Example Middle School"],
        },
    )
    assert profile.status_code == 200
    profile_id = profile.json()["profile_id"]
    assigned = client.patch(f"/api/devices/{device_id}/profile", json={"profile_id": profile_id})
    assert assigned.status_code == 200

    device_headers = {"Authorization": f"Bearer {device_token}"}
    expected_alerts = 0
    for case in corpus:
        response = client.post(
            "/api/events",
            headers=device_headers,
            json={
                "source_type": "browser",
                "app_name": "SyntheticBrowser.exe",
                "window_title": case["id"],
                "profile_id": profile_id,
                "redacted_text": case["text"],
                "capture_scope": "synthetic_e2e",
                "collector_version": "synthetic-e2e",
                "metadata": {"case_id": case["id"]},
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["risk_level"] == case["risk_level"]
        assert body["categories"] == case["categories"]
        if case["risk_level"] in {"medium", "high", "critical"}:
            assert body["alert_id"]
            expected_alerts += 1
        else:
            assert body["alert_id"] is None

    events = client.get("/api/events")
    assert events.status_code == 200
    assert len(events.json()) == len(corpus)

    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    alert_rows = alerts.json()
    assert len(alert_rows) == expected_alerts
    assert {row["severity"] for row in alert_rows} >= {"medium", "high", "critical"}

    alert_id = alert_rows[0]["alert_id"]
    detail = client.get(f"/api/alerts/{alert_id}")
    assert detail.status_code == 200
    assert detail.json()["redacted_text"]
    reviewed = client.post(
        f"/api/alerts/{alert_id}/review",
        json={"status": "reviewed", "notes": "Synthetic E2E reviewed."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"

    exported = client.post("/api/storage/export")
    assert exported.status_code == 200
    export_id = exported.json()["export_id"]
    export_path = tmp_path / "exports" / f"{export_id}.gnexport"
    assert export_path.is_file()
    assert not export_path.read_bytes().startswith(b"PK")
    downloaded = client.get(exported.json()["download_url"])
    assert downloaded.status_code == 200

    cleanup = client.post("/api/settings/retention/run-cleanup")
    assert cleanup.status_code == 200
    assert cleanup.json()["events"] >= 1
    storage = client.get("/api/storage")
    assert storage.status_code == 200
    assert storage.json()["events"] < len(corpus)
