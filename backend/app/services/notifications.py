"""Notification routing.

Channels: dashboard (always recorded), email via SMTP (parent-configured), and a
generic webhook that is compatible with self-hosted/local push services such as
ntfy and Gotify (both accept a JSON POST). Every delivery attempt — success or
failure — is recorded as a NotificationLog row so the Audit page can show a
delivery trail without leaking credentials.
"""
from __future__ import annotations

import base64
import http.client as http_client
import ipaddress
import json
import logging
import smtplib
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from urllib.parse import ParseResult, urlparse, urlunparse

from sqlalchemy.orm import Session

from app.db.models import Alert, NotificationLog, Setting
from app.services import encryption

log = logging.getLogger(__name__)

SEVERITY_ROUTING = {
    "critical": {"immediate": True},
    "high": {"immediate": True},
    "medium": {"digest": True},
    "low": {"dashboard_only": True},
}

_METADATA_HOSTS = {
    "169.254.169.254",
    "100.100.100.200",
    "metadata.google.internal",
    "metadata",
}


@dataclass(frozen=True)
class _WebhookTarget:
    parsed: ParseResult
    host: str
    port: int
    address: str


class _PinnedHTTPSConnection(http_client.HTTPSConnection):
    """Connect to a prevalidated IP while verifying TLS for the URL hostname."""

    def __init__(self, connect_host: str, tls_hostname: str, port: int, timeout: float) -> None:
        super().__init__(tls_hostname, port=port, timeout=timeout)
        self._connect_host = connect_host

    def connect(self) -> None:
        sock = self._create_connection((self._connect_host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _get_smtp_config(session: Session) -> dict[str, Any] | None:
    row = session.query(Setting).filter(Setting.key == "notification_settings").first()
    if not row or not row.value:
        return None
    try:
        cfg = json.loads(row.value)
    except Exception:
        return None
    if not cfg.get("enabled"):
        return None
    enc = cfg.get("password_enc")
    if enc:
        try:
            cfg["password"] = encryption.decrypt_text(base64.b64decode(enc.encode("ascii")))
        except Exception:
            cfg["password"] = ""
    return cfg


def _send_email(cfg: dict[str, Any], subject: str, body: str) -> tuple[bool, str]:
    try:
        msg = EmailMessage()
        msg["From"] = cfg.get("from_address", "guardiannode@localhost")
        msg["To"] = cfg.get("to_address", cfg.get("from_address", ""))
        msg["Subject"] = subject
        msg.set_content(body)
        host = cfg["host"]
        port = int(cfg.get("port", 587))
        tls_mode = cfg.get("tls_mode", "starttls")
        username = cfg.get("username")
        password = cfg.get("password")
        if tls_mode == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if tls_mode == "starttls":
                server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
        server.quit()
        return True, "ok"
    except Exception as e:  # pragma: no cover - depends on a real SMTP server
        log.warning("smtp send failed: %s", e)
        return False, str(e)


def _is_internal_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def _resolve_webhook_target(url: str, *, allow_private: bool = False) -> tuple[_WebhookTarget | None, str]:
    if len(url) > 2048:
        return None, "webhook URL is too long"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None, "webhook URL must start with http:// or https://"
    if parsed.username or parsed.password:
        return None, "webhook URL must not include userinfo"
    if parsed.fragment:
        return None, "webhook URL must not include a fragment"
    try:
        port = parsed.port
    except ValueError:
        return None, "webhook URL has an invalid port"
    if port is not None and not (1 <= port <= 65535):
        return None, "webhook URL has an invalid port"
    if not parsed.hostname:
        return None, "webhook URL must include a host"
    port = port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname.strip().lower().strip("[]").rstrip(".")
    if host in _METADATA_HOSTS:
        return None, "webhook URL targets a cloud metadata service"
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        if not allow_private:
            return None, "private/internal webhook URL requires explicit opt-in"
        return _WebhookTarget(parsed=parsed, host=host, port=port, address="127.0.0.1"), "ok"

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except OSError:
            return None, "webhook URL host could not be resolved"
        for record in records:
            try:
                resolved_ip = ipaddress.ip_address(record[4][0])
            except ValueError:
                return None, "webhook URL resolved to an invalid address"
            if resolved_ip not in addresses:
                addresses.append(resolved_ip)
        if not addresses:
            return None, "webhook URL host could not be resolved"
    else:
        addresses.append(ip)

    for address in addresses:
        if str(address) in _METADATA_HOSTS:
            return None, "webhook URL targets a cloud metadata service"
        if _is_internal_ip(address) and not allow_private:
            return None, "private/internal webhook URL requires explicit opt-in"

    return _WebhookTarget(parsed=parsed, host=host, port=port, address=str(addresses[0])), "ok"


def _validate_webhook_url(url: str, *, allow_private: bool = False) -> tuple[bool, str]:
    target, detail = _resolve_webhook_target(url, allow_private=allow_private)
    return target is not None, detail


def _webhook_path(parsed: ParseResult) -> str:
    return urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))


def _webhook_host_header(host: str, port: int, scheme: str) -> str:
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{host}]" if ":" in host else host
    return display_host if port == default_port else f"{display_host}:{port}"


def _post_webhook(target: _WebhookTarget, body: bytes, *, timeout: float = 20) -> int:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GuardianNode",
        "Host": _webhook_host_header(target.host, target.port, target.parsed.scheme),
    }
    if target.parsed.scheme == "https":
        conn: http_client.HTTPConnection = _PinnedHTTPSConnection(
            target.address,
            target.host,
            target.port,
            timeout,
        )
    else:
        conn = http_client.HTTPConnection(target.address, target.port, timeout=timeout)
    try:
        conn.request("POST", _webhook_path(target.parsed), body=body, headers=headers)
        resp = conn.getresponse()
        status = int(resp.status)
        resp.read(1024)
        return status
    finally:
        conn.close()


def _send_webhook(url: str, payload: dict[str, Any], *, allow_private: bool = False) -> tuple[bool, str]:
    """POST a JSON payload to a generic webhook URL.

    The body uses common field names (``title``/``message``/``priority``) so the
    same call works against ntfy, Gotify, and most generic webhook receivers
    without per-service adapters. Local-only by design: no third-party SaaS.
    """
    target, detail = _resolve_webhook_target(url, allow_private=allow_private)
    if target is None:
        return False, detail
    try:
        body = json.dumps(payload).encode("utf-8")
        status = _post_webhook(target, body)
        if 200 <= int(status) < 300:
            return True, "ok"
        if 300 <= int(status) < 400:
            return False, f"webhook redirects are not followed (HTTP {status})"
        return False, f"webhook returned HTTP {status}"
    except Exception as e:  # pragma: no cover - needs a live endpoint
        log.warning("webhook send failed: %s", e)
        return False, str(e)


def send_test_email(cfg: dict[str, Any]) -> tuple[bool, str]:
    if not cfg.get("enabled"):
        return False, "notifications are disabled"
    if not cfg.get("host"):
        return False, "SMTP host is required"
    return _send_email(
        cfg,
        "[GuardianNode] Test notification",
        "This is a GuardianNode test notification from your local server.",
    )


def send_test_webhook(cfg: dict[str, Any]) -> tuple[bool, str]:
    if not cfg.get("enabled"):
        return False, "notifications are disabled"
    url = cfg.get("webhook_url") or ""
    if not url:
        return False, "webhook URL is required"
    return _send_webhook(
        url,
        {
            "title": "GuardianNode test notification",
            "message": "This is a GuardianNode test notification from your local server.",
            "priority": "default",
            "severity": "test",
        },
        allow_private=bool(cfg.get("webhook_allow_private", False)),
    )


def run_test(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Send a test to every configured channel. Returns one result row per channel.

    Result detail never includes the SMTP password or any secret — only the
    transport-level outcome string.
    """
    results: list[dict[str, Any]] = []
    if cfg.get("host"):
        ok, detail = send_test_email(cfg)
        results.append({"channel": "email", "ok": ok, "detail": detail})
    if cfg.get("webhook_url"):
        ok, detail = send_test_webhook(cfg)
        results.append({"channel": "webhook", "ok": ok, "detail": detail})
    if not results:
        results.append({"channel": "none", "ok": False, "detail": "no channels configured"})
    return results


def dispatch(
    session: Session,
    *,
    alert: Alert,
    risk_summary: str,
    immediate: bool | None = None,
) -> list[NotificationLog]:
    """Dispatch a notification according to severity routing."""
    routing = SEVERITY_ROUTING.get(alert.severity, {})
    is_immediate = immediate if immediate is not None else routing.get("immediate", False)
    logs: list[NotificationLog] = []

    # 1) Dashboard — always recorded (the dashboard reads from alerts table)
    nl = NotificationLog(
        alert_id=alert.alert_id,
        channel="dashboard",
        severity=alert.severity,
        result="ok",
        detail=None,
    )
    session.add(nl)
    logs.append(nl)

    # 2) Email if SMTP configured and severity warrants immediate
    cfg = _get_smtp_config(session)
    if cfg and is_immediate:
        subject = f"[GuardianNode] {alert.severity.upper()} alert"
        body = (
            f"GuardianNode detected a {alert.severity} severity event.\n\n"
            f"Summary: {risk_summary}\n"
            f"Device: {alert.device_id or 'unknown'}\n"
            f"Time: {datetime.now(UTC).isoformat()}\n\n"
            f"Open the dashboard to review."
        )
        ok, detail = _send_email(cfg, subject, body)
        nl = NotificationLog(
            alert_id=alert.alert_id,
            channel="email",
            severity=alert.severity,
            result="ok" if ok else "error",
            detail=detail if not ok else None,
        )
        session.add(nl)
        logs.append(nl)

    # 3) Webhook (ntfy/Gotify/generic) if configured and severity warrants immediate
    if cfg and is_immediate and cfg.get("webhook_url"):
        ok, detail = _send_webhook(
            cfg["webhook_url"],
            {
                "title": f"GuardianNode {alert.severity.upper()} alert",
                "message": risk_summary,
                "priority": "high" if alert.severity in ("critical", "high") else "default",
                "severity": alert.severity,
                "device": alert.device_id or "unknown",
                "time": datetime.now(UTC).isoformat(),
            },
            allow_private=bool(cfg.get("webhook_allow_private", False)),
        )
        nl = NotificationLog(
            alert_id=alert.alert_id,
            channel="webhook",
            severity=alert.severity,
            result="ok" if ok else "error",
            detail=detail if not ok else None,
        )
        session.add(nl)
        logs.append(nl)

    return logs
