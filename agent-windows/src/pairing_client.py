"""Pair with a backend using a 6-digit code (and optional mDNS discovery)."""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.config import default_device_path

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
) -> tuple[str, str]:
    """Run the pair/complete handshake. Returns (device_id, device_token)."""
    body = {
        "code": code.strip(),
        "hostname": hostname,
        "platform": platform,
        "agent_version": agent_version,
    }
    with httpx.Client(timeout=20.0) as c:
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
) -> tuple[str, str]:
    """Enroll the first all-in-one device with the purpose-bound local token."""
    body = {
        "device_bootstrap_token": device_bootstrap_token.strip(),
        "hostname": hostname,
        "platform": platform,
        "agent_version": agent_version,
    }
    with httpx.Client(timeout=20.0) as c:
        r = c.post(f"{backend_url.rstrip('/')}/api/devices/bootstrap-local", json=body)
        r.raise_for_status()
        data = r.json()
    return data["device_id"], data["device_token"]


def save_credentials(device_id: str, token: str, backend_url: str, path: Path | None = None) -> Path:
    path = path or default_device_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"device_id": device_id, "device_token": token, "backend_url": backend_url}),
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

    for attempt in range(1, attempts + 1):
        try:
            if local_bootstrap:
                device_id, token = bootstrap_local_with_server(
                    backend_url, device_bootstrap_token, hostname, agent_version=agent_version,
                )
            else:
                device_id, token = pair_with_server(
                    backend_url, code, hostname, agent_version=agent_version,
                )
            save_credentials(device_id, token, backend_url, device_path)
            pending_path.unlink(missing_ok=True)
            log.info("paired with %s as device %s", backend_url, device_id)
            return {"device_id": device_id, "device_token": token, "backend_url": backend_url}
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
