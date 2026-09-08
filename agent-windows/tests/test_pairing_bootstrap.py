"""Pairing bootstrap: the agent must complete pairing left by the installer."""
from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src import main as agent_main
from src import pairing_client
from src.backend_client import BackendClient
from src.config import AgentConfig


def _pairing_bundle(server_url: str = "https://srv:8787") -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Family CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return {
        "format": "guardiannode-pairing-bundle-v1",
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "server_url": server_url,
        "ca_pem": pem,
        "ca_sha256": digest,
    }


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


def test_bootstrap_removes_stale_pending_when_already_paired(tmp_path):
    device = tmp_path / "device.json"
    device.write_text(json.dumps({
        "device_id": "dev1", "device_token": "tok1", "backend_url": "http://srv:8787",
    }))
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://srv:8787", "local_bootstrap": True}))

    result = pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1",
        pending_path=pending,
        device_path=device,
    )

    assert result["device_token"] == "tok1"
    assert not pending.exists()


def test_bootstrap_pairs_and_saves_credentials(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({
        "backend_url": "https://srv:8787",
        "code": "123456",
        "bundle": _pairing_bundle(),
    }))
    device = tmp_path / "device.json"

    def fake_pair(
        backend_url,
        code,
        hostname,
        platform="windows",
        agent_version="0.1.0-alpha.1",
        **kwargs,
    ):
        assert backend_url == "https://srv:8787"
        assert kwargs["ca_path"].is_file()
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
    assert saved["backend_url"] == "https://srv:8787"
    assert len(saved["ca_sha256"]) == 64
    assert (tmp_path / "family-ca.pem").is_file()
    assert not pending.exists(), "pending file must be removed after success"


def test_manual_pairing_bundle_enrolls_exact_url_and_ca(tmp_path):
    bundle = tmp_path / "family.gnpair"
    bundle_payload = _pairing_bundle()
    bundle.write_text(json.dumps(bundle_payload), encoding="utf-8")

    server_url, ca_path, fingerprint = pairing_client.enroll_pairing_bundle(
        bundle, device_path=tmp_path / "device.json"
    )

    assert server_url == "https://srv:8787"
    assert ca_path == tmp_path / "family-ca.pem"
    assert ca_path.read_text("ascii").startswith("-----BEGIN CERTIFICATE-----")
    assert fingerprint == bundle_payload["ca_sha256"]


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
        **kwargs,
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


def test_bootstrap_can_read_explicit_bootstrap_token_path_for_broker_storage(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({"backend_url": "http://127.0.0.1:8787", "local_bootstrap": True}))
    secure_device = tmp_path / "Secure" / "device.json"
    root_keys = tmp_path / "keys"
    root_keys.mkdir()
    bootstrap_token = root_keys / "device_bootstrap_token.json"
    bootstrap_token.write_text(json.dumps({"token": "broker-bootstrap-secret"}))

    def fake_bootstrap(
        backend_url,
        device_bootstrap_token,
        hostname,
        platform="windows",
        agent_version="0.1.0-alpha.1",
        **kwargs,
    ):
        assert backend_url == "http://127.0.0.1:8787"
        assert device_bootstrap_token == "broker-bootstrap-secret"
        assert hostname == "family-pc"
        return "dev-local", "tok-local"

    monkeypatch.setattr(pairing_client, "bootstrap_local_with_server", fake_bootstrap)
    result = pairing_client.bootstrap_pairing(
        "family-pc",
        "0.1.0-alpha.1",
        pending_path=pending,
        device_path=secure_device,
        bootstrap_token_path=bootstrap_token,
    )

    assert result["device_token"] == "tok-local"
    assert json.loads(secure_device.read_text())["device_token"] == "tok-local"


def test_bootstrap_removes_pending_on_rejected_code(tmp_path, monkeypatch):
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({
        "backend_url": "https://srv:8787",
        "code": "999999",
        "bundle": _pairing_bundle(),
    }))

    def fake_pair(*args, **kwargs):
        req = httpx.Request("POST", "https://srv:8787/api/devices/pair/complete")
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
    pending.write_text(json.dumps({
        "backend_url": "https://srv:8787",
        "code": "123456",
        "bundle": _pairing_bundle(),
    }))

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


def test_bootstrap_rejects_ca_fingerprint_mismatch(tmp_path, monkeypatch):
    bundle = _pairing_bundle()
    bundle["ca_sha256"] = "00" * 32
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({
        "backend_url": "https://srv:8787", "code": "123456", "bundle": bundle,
    }))
    monkeypatch.setattr(
        pairing_client,
        "pair_with_server",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not connect")),
    )

    assert pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=tmp_path / "device.json",
    ) is None
    assert pending.exists()
    assert not (tmp_path / "family-ca.pem").exists()


def test_bootstrap_rejects_expired_pairing_bundle(tmp_path, monkeypatch):
    bundle = _pairing_bundle()
    bundle["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    pending = tmp_path / "pending_pairing.json"
    pending.write_text(json.dumps({
        "backend_url": "https://srv:8787", "code": "123456", "bundle": bundle,
    }))
    monkeypatch.setattr(
        pairing_client,
        "pair_with_server",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not connect")),
    )

    assert pairing_client.bootstrap_pairing(
        "kid-pc", "0.1.0-alpha.1", pending_path=pending, device_path=tmp_path / "device.json",
    ) is None


def test_pairing_rejects_non_loopback_http() -> None:
    with pytest.raises(ValueError, match="requires HTTPS"):
        pairing_client.pair_with_server("http://192.0.2.10:8787", "123456", "kid-pc")


def test_backend_client_requires_enrolled_ca_for_https() -> None:
    client = BackendClient("https://srv:8787", "token")
    with pytest.raises(RuntimeError, match="family CA"):
        client._verify()


@pytest.mark.asyncio
async def test_refresh_pairing_credentials_updates_live_client(monkeypatch):
    client = BackendClient("http://old:8787", "")
    cfg = AgentConfig(backend_url="http://old:8787")

    def fake_bootstrap(hostname, agent_version, *, attempts=5, retry_delay=10.0):
        assert hostname == "kid-pc"
        assert attempts == 1
        assert retry_delay == 0.0
        return {
            "device_id": "dev-live",
            "device_token": "tok-live",
            "backend_url": "http://new:8787/",
        }

    monkeypatch.setattr(agent_main, "bootstrap_pairing", fake_bootstrap)

    changed = await agent_main.refresh_pairing_credentials(client, cfg, hostname="kid-pc")

    assert changed is True
    assert client.base_url == "http://new:8787"
    assert client.token == "tok-live"
    assert cfg.backend_url == "http://new:8787"
    assert cfg.device_id == "dev-live"
    assert cfg.device_token == "tok-live"


@pytest.mark.asyncio
async def test_refresh_pairing_credentials_skips_already_paired(monkeypatch):
    client = BackendClient("http://old:8787", "already-token")
    cfg = AgentConfig(backend_url="http://old:8787", device_token="already-token")

    def fail_bootstrap(*args, **kwargs):
        raise AssertionError("bootstrap should not run when a token is already loaded")

    monkeypatch.setattr(agent_main, "bootstrap_pairing", fail_bootstrap)

    changed = await agent_main.refresh_pairing_credentials(client, cfg, hostname="kid-pc")

    assert changed is False
    assert client.token == "already-token"
