"""Pairing bootstrap: the agent must complete pairing left by the installer."""
from __future__ import annotations

import json

import httpx

from src import pairing_client


def test_bootstrap_noop_without_pending_file(tmp_path):
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1",
        pending_path=tmp_path / "pending_pairing.json",
        device_path=tmp_path / "device.json",
    )
    assert result is None


def test_bootstrap_returns_existing_credentials(tmp_path):
    device = tmp_path / "device.json"
    device.write_text(json.dumps({
        "device_id": "dev1", "device_token": "tok1", "backend_url": "http://srv:8787",
    }))
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1",
        pending_path=tmp_path / "pending_pairing.json",
        device_path=device,
    )
    assert result["device_token"] == "tok1"


def test_bootstrap_pairs_and_saves_credentials(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "123456"}))
    device = tmp_path / "device.json"

    def fake_pair(
        backend_url,
        code,
        hostname,
        platform="windows",
        agent_version="0.1.0-alpha.1",
    ):
        assert backend_url == "http://srv:8787"
        assert code == "123456"
        assert hostname == "kid-pc"
        return "dev42", "token42"

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=device,
    )
    assert result["device_id"] == "dev42"
    saved = json.loads(device.read_text())
    assert saved["device_token"] == "token42"
    assert saved["backend_url"] == "http://srv:8787"
    assert not pending.exists(), "pending file must be removed after success"


def test_bootstrap_reads_device_token_for_local_bootstrap(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://127.0.0.1:8787", "local_bootstrap": True}))
    device = tmp_path / "device.json"
    token_dir = tmp_path / "keys"
    token_dir.mkdir()
    (token_dir / "device_bootstrap_token.json").write_text(json.dumps({"token": "device-secret"}))

    def fake_bootstrap(
        backend_url,
        device_bootstrap_token,
        hostname,
        platform="windows",
        agent_version="0.1.0-alpha.1",
    ):
        assert backend_url == "http://127.0.0.1:8787"
        assert device_bootstrap_token == "device-secret"
        assert hostname == "family-pc"
        return "dev-local", "tok-local"

    monkeypatch.setattr(pairing_client, "bootstrap_local_with_server", fake_bootstrap)
    result = pairing_client.bootstrap_pairing(
        "family-pc", "0.1.0-alpha.1", pending_path=pending, device_path=device,
    )
    assert result["device_id"] == "dev-local"


def test_bootstrap_removes_pending_on_rejected_code(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "999999"}))

    def fake_pair(*args, **kwargs):
        req = httpx.Request("POST", "http://srv:8787/api/devices/pair/complete")
        resp = httpx.Response(400, request=req)
        raise httpx.HTTPStatusError("rejected", request=req, response=resp)

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=tmp_path / "device.json",
    )
    assert result is None
    assert not pending.exists(), "rejected single-use code must not be retried forever"


def test_bootstrap_keeps_pending_on_local_bootstrap_auth_failure(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({
        "backend_url": "http://127.0.0.1:8787",
        "local_bootstrap": True,
        "device_bootstrap_token": "stale-token",
    }))

    def fake_bootstrap(*args, **kwargs):
        req = httpx.Request("POST", "http://127.0.0.1:8787/api/devices/bootstrap-local")
        resp = httpx.Response(401, request=req)
        raise httpx.HTTPStatusError("rejected", request=req, response=resp)

    monkeypatch.setattr(pairing_client, "bootstrap_local_with_server", fake_bootstrap)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=tmp_path / "device.json",
    )
    assert result is None
    assert pending.exists(), "installer repair must be able to resume local bootstrap"


def test_bootstrap_keeps_pending_on_transient_failure(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "123456"}))

    def fake_pair(*args, **kwargs):
        raise httpx.ConnectError("server still booting")

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1",
        pending_path=pending,
        device_path=tmp_path / "device.json",
        attempts=2,
        retry_delay=0.01,
    )
    assert result is None
    assert pending.exists(), "transient failures retry on next agent start"


def test_bootstrap_refuses_mdns_discovery_without_explicit_url(tmp_path, monkeypatch):
    """mDNS discovery is advisory only; it must not choose a backend."""
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"code": "123456"}))  # no backend_url → discovery

    monkeypatch.setattr(pairing_client, "discover_servers", lambda timeout=3.0: [
        pairing_client.DiscoveredServer(name="srv._guardiannode._tcp.local.", host="10.0.0.2", port=8787),
    ])

    def fake_pair(*args, **kwargs):  # must not be reached
        raise AssertionError("pairing attempted despite unauthenticated mDNS discovery")

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=tmp_path / "device.json",
    )
    assert result is None
    assert pending.exists(), "pending pairing should remain for explicit retry"
