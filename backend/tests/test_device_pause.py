"""Regression tests: pause state must expire, never silently disable protection."""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.models import Device, Event, ScreenshotUploadReceipt
from app.services import pipeline_metrics, rate_limit
from app.services.device_state import effective_paused_until, is_device_paused

_JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "////2wBDAf//////////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIA"
    "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAVEAEBAAAAAAAAAAAAAAAAAAAAEf/aAAwDAQACEAMQAAAB9A//"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAU"
    "EQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Aqf/xAAUEAE"
    "AAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQ"
    "MBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEA"
    "AT8QH//Z"
)


def _client(monkeypatch, tmp_path) -> TestClient:
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
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def _pair(client: TestClient) -> tuple[str, str]:
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token

    r = client.post(
        "/api/devices/bootstrap-local",
        json={
            "hostname": "kid-pc",
            "platform": "windows",
            "agent_version": "0.1.0-alpha.1",
            "device_bootstrap_token": ensure_device_bootstrap_token(),
        },
    )
    assert r.status_code == 200
    return r.json()["device_id"], r.json()["device_token"]


def _set_paused_until(device_id: str, until: datetime | None, status: str = "paused") -> None:
    from app.db.session import get_sessionmaker

    s = get_sessionmaker()()
    try:
        d = s.get(Device, device_id)
        d.paused_until = until
        d.status = status
        s.commit()
    finally:
        s.close()


def _event_count() -> int:
    from app.db.session import get_sessionmaker

    s = get_sessionmaker()()
    try:
        return s.query(Event).count()
    finally:
        s.close()


def _pending_count() -> int:
    from app.services import screenshot_async

    return screenshot_async.pending_count()


def _receipt_count() -> int:
    from app.db.session import get_sessionmaker

    s = get_sessionmaker()()
    try:
        return s.query(ScreenshotUploadReceipt).count()
    finally:
        s.close()


# ---- helper unit behavior -------------------------------------------------

def test_helper_null_pause_is_not_paused():
    d = Device(device_id="x", hostname="h", paused_until=None, status="online")
    assert is_device_paused(d) is False


def test_helper_active_pause_is_paused():
    d = Device(
        device_id="x", hostname="h", status="paused",
        paused_until=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert is_device_paused(d) is True
    assert effective_paused_until(d) is not None


def test_helper_expired_pause_is_cleared_and_status_restored():
    d = Device(
        device_id="x", hostname="h", status="paused",
        paused_until=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert is_device_paused(d) is False
    assert d.paused_until is None
    assert d.status == "online"
    assert effective_paused_until(d) is None


def test_helper_handles_naive_datetimes_from_sqlite():
    # SQLite hands back naive datetimes; they are stored as UTC.
    naive_now = datetime.now(UTC).replace(tzinfo=None)
    d = Device(
        device_id="x", hostname="h", status="paused",
        paused_until=naive_now + timedelta(minutes=5),  # naive
    )
    assert is_device_paused(d) is True
    d.paused_until = naive_now - timedelta(minutes=5)  # naive, past
    assert is_device_paused(d) is False
    assert d.paused_until is None


# ---- API behavior -----------------------------------------------------------

def test_active_pause_blocks_event_ingest(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) + timedelta(hours=1))

    r = client.post(
        "/api/events",
        json={"source_type": "ocr", "redacted_text": "free robux click here"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["risk_id"] is None
    assert _event_count() == 0


def test_expired_pause_does_not_block_event_ingest(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) - timedelta(seconds=5))

    r = client.post(
        "/api/events",
        json={"source_type": "ocr", "redacted_text": "hello world"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["event_id"]
    assert _event_count() == 1


def test_active_pause_blocks_screenshot_ingest(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) + timedelta(hours=1))

    r = client.post(
        "/api/events/screenshot",
        files={"image": ("frame.jpg", _JPEG_1X1, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paused"
    assert r.json()["queued"] is False


def test_expired_pause_does_not_block_screenshot_ingest(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) - timedelta(seconds=5))

    r = client.post(
        "/api/events/screenshot",
        files={"image": ("frame.jpg", _JPEG_1X1, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert r.json()["queued"] is True


def test_screenshot_idempotency_key_deduplicates_retries(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _device_id, token = _pair(client)
    headers = {"Authorization": f"Bearer {token}"}
    data = {"idempotency_key": "retry-key-1", "age_group": "10_13"}

    first = client.post(
        "/api/events/screenshot",
        files={"image": ("frame.jpg", _JPEG_1X1, "image/jpeg")},
        data=data,
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["status"] == "queued"

    second = client.post(
        "/api/events/screenshot",
        files={"image": ("frame.jpg", _JPEG_1X1, "image/jpeg")},
        data=data,
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json() == first.json()
    assert _pending_count() == 1
    assert _receipt_count() == 1


def test_capture_config_reports_pause_accurately(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/devices/capture-config", headers=headers)
    assert r.status_code == 200
    assert r.json()["paused"] is False

    _set_paused_until(device_id, datetime.now(UTC) + timedelta(hours=1))
    r = client.get("/api/devices/capture-config", headers=headers)
    assert r.json()["paused"] is True
    assert r.json()["paused_until"] is not None

    _set_paused_until(device_id, datetime.now(UTC) - timedelta(seconds=5))
    r = client.get("/api/devices/capture-config", headers=headers)
    assert r.json()["paused"] is False


def test_expired_pause_cleared_server_side(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) - timedelta(seconds=5))

    # Any pause-aware endpoint should self-heal the stale row.
    r = client.post(
        "/api/devices/heartbeat",
        json={"queued_frames": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["paused_until"] is None

    from app.db.session import get_sessionmaker
    s = get_sessionmaker()()
    try:
        d = s.get(Device, device_id)
        assert d.paused_until is None
        assert d.status == "online"
    finally:
        s.close()


def test_device_list_clears_stale_paused_badge(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    device_id, _token = _pair(client)
    _set_paused_until(device_id, datetime.now(UTC) - timedelta(minutes=2))

    # Log in as parent (first-run setup) to list devices.
    from app.services.setup_token import ensure_setup_token
    setup_token = ensure_setup_token()
    r = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": "correct-horse-battery",
            "recovery_code": "alpha bravo gamma delta",
            "setup_token": setup_token,
        },
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/devices")
    assert r.status_code == 200
    dev = next(d for d in r.json() if d["device_id"] == device_id)
    assert dev["paused_until"] is None
    assert dev["status"] == "online"
