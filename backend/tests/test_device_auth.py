"""Device token format, O(1) verification, legacy fallback, and abuse limits."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import Device
from app.services import device_tokens, pipeline_metrics, rate_limit
from app.services.parent_auth import hash_password


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


def test_token_format_embeds_device_id():
    token, _hash = device_tokens.issue_token("01ABCDEF")
    assert token.startswith("gn_dev_01ABCDEF_")
    parsed = device_tokens.parse_token(token)
    assert parsed is not None
    device_id, secret = parsed
    assert device_id == "01ABCDEF"
    assert len(secret) >= 32


def test_parse_rejects_legacy_and_garbage():
    assert device_tokens.parse_token("some-legacy-opaque-token") is None
    assert device_tokens.parse_token("gn_dev_") is None
    assert device_tokens.parse_token("gn_dev_onlyid") is None


def test_new_pairing_issues_structured_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token

    r = client.post(
        "/api/devices/bootstrap-local",
        json={"hostname": "kid-pc", "device_bootstrap_token": ensure_device_bootstrap_token()},
    )
    assert r.status_code == 200
    token = r.json()["device_token"]
    device_id = r.json()["device_id"]
    assert token.startswith(f"gn_dev_{device_id}_")

    # And it authenticates.
    r = client.post(
        "/api/devices/heartbeat", json={"queued_frames": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_legacy_opaque_token_still_authenticates(db_session):
    legacy = "legacy-token-from-an-old-pairing"
    db_session.add(Device(
        device_id="olddev", hostname="old-pc", paired=True,
        token_hash=hash_password(legacy),
    ))
    db_session.commit()
    device = device_tokens.authenticate(db_session, legacy)
    assert device is not None and device.device_id == "olddev"


def test_structured_token_with_wrong_secret_fails(db_session):
    token, token_hash = device_tokens.issue_token("dev1")
    db_session.add(Device(device_id="dev1", hostname="pc", paired=True, token_hash=token_hash))
    db_session.commit()
    assert device_tokens.authenticate(db_session, token) is not None
    assert device_tokens.authenticate(db_session, "gn_dev_dev1_wrongsecret") is None
    assert device_tokens.authenticate(db_session, "gn_dev_otherdev_whatever") is None


def test_structured_token_full_hash_upgrade_fallback(db_session):
    token, _token_hash = device_tokens.issue_token("dev1")
    db_session.add(Device(
        device_id="dev1",
        hostname="pc",
        paired=True,
        token_hash=hash_password(token),
    ))
    db_session.commit()
    assert device_tokens.authenticate(db_session, token) is not None


def test_revoked_device_token_fails(db_session):
    token, token_hash = device_tokens.issue_token("dev1")
    db_session.add(Device(device_id="dev1", hostname="pc", paired=False, token_hash=token_hash))
    db_session.commit()
    assert device_tokens.authenticate(db_session, token) is None


def test_repeated_invalid_device_auth_is_rate_limited(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for _ in range(rate_limit.MAX_FAILURES):
        r = client.post(
            "/api/devices/heartbeat", json={"queued_frames": 0},
            headers={"Authorization": "Bearer gn_dev_bogus_bogus"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/devices/heartbeat", json={"queued_frames": 0},
        headers={"Authorization": "Bearer gn_dev_bogus_bogus"},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_valid_structured_token_clears_existing_ip_block(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token
    pair = client.post(
        "/api/devices/bootstrap-local",
        json={"hostname": "kid-pc", "device_bootstrap_token": ensure_device_bootstrap_token()},
    )
    assert pair.status_code == 200
    token = pair.json()["device_token"]

    for _ in range(rate_limit.MAX_FAILURES):
        r = client.post(
            "/api/devices/heartbeat",
            json={"queued_frames": 0},
            headers={"Authorization": "Bearer gn_dev_bogus_bogus"},
        )
        assert r.status_code == 401

    r = client.post(
        "/api/devices/heartbeat",
        json={"queued_frames": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_valid_auth_resets_failure_count(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token
    r = client.post(
        "/api/devices/bootstrap-local",
        json={"hostname": "kid-pc", "device_bootstrap_token": ensure_device_bootstrap_token()},
    )
    token = r.json()["device_token"]

    for _ in range(rate_limit.MAX_FAILURES - 1):
        client.post(
            "/api/devices/heartbeat", json={"queued_frames": 0},
            headers={"Authorization": "Bearer wrong"},
        )
    r = client.post(
        "/api/devices/heartbeat", json={"queued_frames": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # Failure window reset: more attempts allowed again.
    r = client.post(
        "/api/devices/heartbeat", json={"queued_frames": 0},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401
