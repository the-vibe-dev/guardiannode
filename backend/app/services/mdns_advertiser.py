"""mDNS / Zeroconf advertiser.

The backend can announce itself on the LAN as `_guardiannode._tcp.local`.
Discovery is advisory only; child installs still require an explicit trusted
server URL.
"""
from __future__ import annotations

import logging
import socket

from app.settings import settings

log = logging.getLogger(__name__)

try:
    from zeroconf import ServiceInfo, Zeroconf  # type: ignore
    _HAS_ZEROCONF = True
except ImportError:  # pragma: no cover
    _HAS_ZEROCONF = False
    ServiceInfo = None  # type: ignore
    Zeroconf = None  # type: ignore


_SERVICE_TYPE = "_guardiannode._tcp.local."

_zc: Zeroconf | None = None
_info: ServiceInfo | None = None


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "guardiannode"


def _local_ipv4() -> bytes | None:
    """Best-effort local IP discovery. Returns packed 4 bytes or None."""
    try:
        # Trick: connect a UDP socket to a public-looking address to discover
        # the default outbound interface without actually sending.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return socket.inet_aton(ip)
    except Exception:
        return None


def start() -> None:
    """Start the mDNS advertiser. Safe to call multiple times (idempotent)."""
    global _zc, _info
    if not settings.mdns_enabled:
        log.info("mDNS advertiser disabled by setting")
        return
    if not _HAS_ZEROCONF:
        log.warning("zeroconf not installed; mDNS advertise skipped")
        return
    if _zc is not None:
        return

    host = _hostname()
    addr = _local_ipv4()
    if addr is None:
        log.warning("could not determine local IP; mDNS advertise skipped")
        return

    name = f"{host}.{_SERVICE_TYPE}"
    port = settings.bind_port

    properties = {
        b"version": b"0.1.0-alpha.2",
        b"path": b"/api",
        b"pairing": b"/api/devices/pair",
    }

    _info = ServiceInfo(
        type_=_SERVICE_TYPE,
        name=name,
        addresses=[addr],
        port=port,
        properties=properties,
        server=f"{host}.local.",
    )
    _zc = Zeroconf()
    _zc.register_service(_info)
    log.info("mDNS service registered: %s on port %d", name, port)


def stop() -> None:
    global _zc, _info
    if _zc is None:
        return
    try:
        if _info is not None:
            _zc.unregister_service(_info)
        _zc.close()
    except Exception:
        pass
    _zc = None
    _info = None
