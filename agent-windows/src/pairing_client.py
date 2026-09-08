"""Pair with a backend using a 6-digit code (and optional mDNS discovery)."""
from __future__ import annotations

import json
import hashlib
import hmac
import logging
import os
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from src.config import default_device_path
from src.family_tls import family_ca_ssl_context

log = logging.getLogger(__name__)

_SERVICE_TYPE = "_guardiannode._tcp.local."


@dataclass
class DiscoveredServer:
    name: str
    host: str
    port: int


def discover_servers(timeout: float = 3.0) -> list[DiscoveredServer]:
    """Browse mDNS for GuardianNode servers on the local network."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf  # type: ignore
    except ImportError:
        log.warning("zeroconf not installed; mDNS discovery disabled")
        return []

    found: dict[str, DiscoveredServer] = {}

    class _Listener:
        def add_service(self, zc, type_, name):  # noqa: D401, ANN001
            try:
                info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
                if not info:
                    return
                host = ""
                for addr in info.addresses or []:
                    if len(addr) == 4:
                        host = socket.inet_ntoa(addr)
                        break
                if host:
                    found[name] = DiscoveredServer(name=name, host=host, port=info.port or 8787)
            except Exception:
                pass

        def remove_service(self, zc, type_, name):  # noqa: D401, ANN001
            pass

        def update_service(self, zc, type_, name):  # noqa: D401, ANN001
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, _SERVICE_TYPE, _Listener())
        time.sleep(timeout)
    finally:
        try:
            zc.close()
        except Exception:
            pass
    return list(found.values())


def pair_with_server(
    backend_url: str,
    code: str,
    hostname: str,
    platform: str = "windows",
    agent_version: str = "0.1.0-alpha.3",
    *,
    ca_path: Path | str | None = None,
    allow_loopback_http: bool = False,
) -> tuple[str, str]:
    """Run the pair/complete handshake. Returns (device_id, device_token)."""
    body = {
        "code": code.strip(),
        "hostname": hostname,
        "platform": platform,
        "agent_version": agent_version,
    }
    verify = _transport_verify(backend_url, ca_path, allow_loopback_http=allow_loopback_http)
    with httpx.Client(timeout=20.0, verify=verify) as c:
        r = c.post(f"{backend_url.rstrip('/')}/api/devices/pair/complete", json=body)
        r.raise_for_status()
        data = r.json()
    return data["device_id"], data["device_token"]


def bootstrap_local_with_server(
    backend_url: str,
    device_bootstrap_token: str,
    hostname: str,
    platform: str = "windows",
    agent_version: str = "0.1.0-alpha.3",
    *,
    ca_path: Path | str | None = None,
) -> tuple[str, str]:
    """Enroll the first all-in-one device with the purpose-bound local token."""
    body = {
        "device_bootstrap_token": device_bootstrap_token.strip(),
        "hostname": hostname,
        "platform": platform,
        "agent_version": agent_version,
    }
    verify = _transport_verify(backend_url, ca_path, allow_loopback_http=True)
    with httpx.Client(timeout=20.0, verify=verify) as c:
        r = c.post(f"{backend_url.rstrip('/')}/api/devices/bootstrap-local", json=body)
        r.raise_for_status()
        data = r.json()
    return data["device_id"], data["device_token"]


def save_credentials(
    device_id: str,
    token: str,
    backend_url: str,
    path: Path | None = None,
    *,
    ca_path: Path | str | None = None,
    ca_sha256: str = "",
) -> Path:
    path = path or default_device_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "device_id": device_id,
            "device_token": token,
            "backend_url": backend_url,
            "ca_path": str(ca_path) if ca_path else "",
            "ca_sha256": ca_sha256.lower(),
        }),
        encoding="utf-8",
    )
    # The device token authenticates this child PC to the backend; keep the
    # file owner-only where the OS supports it (Windows relies on the
    # installer's ProgramData ACL instead).
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def load_credentials(path: Path | None = None) -> dict | None:
    path = path or default_device_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8-sig"))
    except Exception:
        return None


def pending_pairing_path() -> Path:
    """Installer drop-file with the wizard's server URL + pairing code."""
    return default_device_path().parent / "pending_pairing.json"


def default_ca_path(device_path: Path | None = None) -> Path:
    """Broker-owned copy of the enrolled family CA."""
    return (device_path or default_device_path()).parent / "family-ca.pem"


def enroll_pairing_bundle(
    bundle_path: Path,
    *,
    backend_url: str | None = None,
    device_path: Path | None = None,
) -> tuple[str, Path, str]:
    """Validate a parent-exported bundle and enroll its CA for manual pairing."""
    try:
        bundle = json.loads(bundle_path.read_text("utf-8-sig"))
    except Exception as exc:
        raise ValueError("pairing bundle is unreadable") from exc
    if not isinstance(bundle, dict):
        raise ValueError("unsupported pairing bundle format")
    enrolled_url = str(backend_url or bundle.get("server_url") or "").rstrip("/")
    if not enrolled_url:
        raise ValueError("pairing bundle has no server URL")
    ca_path, fingerprint = _enroll_bundle(
        {"bundle": bundle}, enrolled_url, device_path
    )
    if ca_path is None:
        raise ValueError("pairing bundle did not enroll a family CA")
    return enrolled_url, ca_path, fingerprint


def _transport_verify(
    backend_url: str,
    ca_path: Path | str | None,
    *,
    allow_loopback_http: bool,
) -> bool | ssl.SSLContext:
    parsed = urlsplit(backend_url)
    if parsed.scheme == "https":
        if not ca_path:
            raise ValueError("HTTPS pairing requires a GuardianNode pairing bundle with a pinned CA")
        path = Path(ca_path)
        if not path.is_file():
            raise ValueError("the enrolled GuardianNode family CA is missing")
        return family_ca_ssl_context(path)
    if parsed.scheme == "http" and allow_loopback_http and parsed.hostname in {"127.0.0.1", "::1", "localhost"}:
        return True
    raise ValueError("pairing requires HTTPS; HTTP is allowed only for loopback bootstrap")


def _parse_expiry(value: object) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("pairing bundle has an invalid expiry") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _enroll_bundle(
    pending: dict,
    backend_url: str,
    device_path: Path | None,
) -> tuple[Path | None, str]:
    """Validate and persist an authenticated CA supplied out-of-band by the parent."""
    bundle = pending.get("bundle")
    bundle_path = str(pending.get("bundle_path") or "").strip()
    if bundle is None and bundle_path:
        try:
            bundle = json.loads(Path(bundle_path).read_text("utf-8-sig"))
        except Exception as exc:
            raise ValueError("pairing bundle is unreadable") from exc
    if bundle is None:
        ca_source_path = str(pending.get("ca_path") or "").strip()
        if ca_source_path:
            pem = Path(ca_source_path).read_text("ascii")
            bundle = {
                "format": "guardiannode-pairing-bundle-v1",
                "server_url": backend_url,
                "expires_at": pending.get("expires_at") or "2999-01-01T00:00:00+00:00",
                "ca_pem": pem,
                "ca_sha256": pending.get("ca_sha256") or _certificate_fingerprint(pem),
            }
    parsed = urlsplit(backend_url)
    if bundle is None:
        if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}:
            return None, ""
        raise ValueError("HTTPS pairing requires the .gnpair bundle downloaded by the parent")
    if not isinstance(bundle, dict) or bundle.get("format") != "guardiannode-pairing-bundle-v1":
        raise ValueError("unsupported pairing bundle format")
    if _parse_expiry(bundle.get("expires_at")) <= datetime.now(UTC):
        raise ValueError("pairing bundle has expired")
    bundle_url = str(bundle.get("server_url") or "").rstrip("/")
    if bundle_url != backend_url.rstrip("/"):
        raise ValueError("pairing bundle server URL does not match the requested server")
    pem = str(bundle.get("ca_pem") or "")
    actual = _certificate_fingerprint(pem)
    expected = str(bundle.get("ca_sha256") or "").lower().replace(":", "")
    if not expected or not hmac.compare_digest(actual, expected):
        raise ValueError("pairing bundle CA fingerprint mismatch")
    enrolled = default_ca_path(device_path)
    _restricted_write(enrolled, pem.encode("ascii"))
    return enrolled, actual


def _certificate_fingerprint(pem: str) -> str:
    try:
        cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    except Exception as exc:
        raise ValueError("pairing bundle CA certificate is invalid") from exc
    now = datetime.now(UTC)
    if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= now:
        raise ValueError("pairing bundle CA certificate is not currently valid")
    try:
        constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    except x509.ExtensionNotFound as exc:
        raise ValueError("pairing bundle certificate is not a CA") from exc
    if not constraints.ca:
        raise ValueError("pairing bundle certificate is not a CA")
    der = cert.public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(der).hexdigest()


def _restricted_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_local_device_bootstrap_token(
    device_path: Path | None = None,
    token_path: Path | None = None,
) -> str | None:
    path = token_path or (device_path or default_device_path()).parent / "keys" / "device_bootstrap_token.json"
    try:
        data = json.loads(path.read_text("utf-8"))
        return str(data.get("token") or "").strip() or None
    except Exception:
        return None


def bootstrap_pairing(
    hostname: str,
    agent_version: str,
    *,
    pending_path: Path | None = None,
    device_path: Path | None = None,
    bootstrap_token_path: Path | None = None,
    attempts: int = 5,
    retry_delay: float = 10.0,
) -> dict | None:
    """Complete pairing from the installer's pending_pairing.json, if present.

    Returns saved credentials on success, existing credentials if already
    paired, or None if there is nothing to do / pairing failed. The pending
    file is deleted on success and on a definitive rejection (HTTP 4xx —
    the code is single-use and expires in 10 minutes, so retrying a rejected
    code is pointless). Transient errors (server still booting, network)
    are retried a few times, then left pending for the next agent start.
    """
    pending_path = pending_path or pending_pairing_path()
    creds = load_credentials(device_path)
    if creds and creds.get("device_token"):
        if pending_path.exists():
            try:
                pending_path.unlink()
            except Exception as e:
                log.warning("could not remove stale pending_pairing.json: %s", e)
        return creds

    if not pending_path.exists():
        return None
    try:
        pending = json.loads(pending_path.read_text("utf-8"))
    except Exception:
        log.error("pending_pairing.json is unreadable; removing it")
        pending_path.unlink(missing_ok=True)
        return None

    code = str(pending.get("code", "")).strip()
    backend_url = str(pending.get("backend_url", "")).strip()
    local_bootstrap = bool(pending.get("local_bootstrap", False))
    device_bootstrap_token = str(pending.get("device_bootstrap_token", "")).strip()
    if local_bootstrap and not device_bootstrap_token:
        device_bootstrap_token = _read_local_device_bootstrap_token(device_path, bootstrap_token_path) or ""
    if not code and not local_bootstrap:
        log.error("pending pairing file has no code; removing it")
        pending_path.unlink(missing_ok=True)
        return None

    if not backend_url:
        servers = discover_servers()
        if not servers:
            log.warning("no backend URL in pending pairing and no server discovered via mDNS")
            return None
        # mDNS only discovers a service; it does not authenticate that the
        # service is the parent's GuardianNode backend. Require the parent to
        # enter the URL explicitly until enrollment can pin a server identity.
        log.error(
            "GuardianNode server discovered via mDNS, but automatic trust is disabled. "
            "Set the backend URL explicitly in the installer. Found: %s",
            ", ".join(f"{s.name} @ {s.host}:{s.port}" for s in servers),
        )
        return None

    try:
        ca_path, ca_sha256 = _enroll_bundle(pending, backend_url, device_path)
    except (OSError, ValueError) as exc:
        log.error("pairing trust validation failed: %s", exc)
        return None

    for attempt in range(1, attempts + 1):
        try:
            if local_bootstrap:
                device_id, token = bootstrap_local_with_server(
                    backend_url, device_bootstrap_token, hostname, agent_version=agent_version,
                    ca_path=ca_path,
                )
            else:
                device_id, token = pair_with_server(
                    backend_url, code, hostname, agent_version=agent_version,
                    ca_path=ca_path,
                )
            save_credentials(
                device_id, token, backend_url, device_path,
                ca_path=ca_path, ca_sha256=ca_sha256,
            )
            pending_path.unlink(missing_ok=True)
            log.info("paired with %s as device %s", backend_url, device_id)
            return {
                "device_id": device_id,
                "device_token": token,
                "backend_url": backend_url,
                "ca_path": str(ca_path) if ca_path else "",
                "ca_sha256": ca_sha256,
            }
        except httpx.HTTPStatusError as e:
            log.error("pairing rejected by %s: %s", backend_url, e.response.status_code)
            if 400 <= e.response.status_code < 500:
                if local_bootstrap and e.response.status_code in {401, 403}:
                    log.warning("local bootstrap still pending; use installer repair to issue a fresh device token")
                    return None
                pending_path.unlink(missing_ok=True)
                return None
        except Exception as e:
            log.warning("pairing attempt %d/%d failed: %s", attempt, attempts, e)
        if attempt < attempts:
            time.sleep(retry_delay)
    log.warning("pairing not completed; will retry on next agent start")
    return None
