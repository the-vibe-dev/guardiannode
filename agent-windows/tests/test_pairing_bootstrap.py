"""Pairing bootstrap: the agent must complete pairing left by the installer."""
from __future__ import annotations

import json

import httpx
import pytest

from src import pairing_client


def test_bootstrap_noop_without_pending_file(tmp_path):
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0",
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
        "kid-pc", "0.1.0",
        pending_path=tmp_path / "pending_pairing.json",
        device_path=device,
    )
    assert result["device_token"] == "tok1"


def test_bootstrap_pairs_and_saves_credentials(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "123456"}))
    device = tmp_path / "device.json"

    def fake_pair(backend_url, code, hostname, platform="windows", agent_version="0.1.0", local_bootstrap=False):
        assert backend_url == "http://srv:8787"
        assert code == "123456"
        assert hostname == "kid-pc"
        return "dev42", "token42"

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0", pending_path=pending, device_path=device,
    )
    assert result["device_id"] == "dev42"
    saved = json.loads(device.read_text())
    assert saved["device_token"] == "token42"
    assert saved["backend_url"] == "http://srv:8787"
    assert not pending.exists(), "pending file must be removed after success"


def test_bootstrap_removes_pending_on_rejected_code(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "999999"}))

    def fake_pair(*args, **kwargs):
        req = httpx.Request("POST", "http://srv:8787/api/devices/pair/complete")
        resp = httpx.Response(400, request=req)
        raise httpx.HTTPStatusError("rejected", request=req, response=resp)

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0", pending_path=pending, device_path=tmp_path / "device.json",
    )
    assert result is None
    assert not pending.exists(), "rejected single-use code must not be retried forever"


def test_bootstrap_keeps_pending_on_transient_failure(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "code": "123456"}))

    def fake_pair(*args, **kwargs):
        raise httpx.ConnectError("server still booting")

    monkeypatch.setattr(pairing_client, "pair_with_server", fake_pair)
    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0",
        pending_path=pending,
        device_path=tmp_path / "device.json",
        attempts=2,
        retry_delay=0.01,
    )
    assert result is None
    assert pending.exists(), "transient failures retry on next agent start"
