"""Notification routing.

Channels: dashboard (always recorded), email via SMTP (parent-configured), and a
generic webhook using the GuardianNode JSON payload. Provider-specific adapters
are required for services with a different API contract. Every delivery attempt — success or
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
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from urllib.parse import ParseResult, urlparse, urlunparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Alert, ChildProfile, NotificationJob, NotificationLog, RiskResult, Setting
from app.services import consent, encryption, profile_policy

log = logging.getLogger(__name__)

POLICY_SUPPRESSED = "delivery_suppressed_by_current_policy"


def immediate_min_severity(session: Session, *, refresh: bool = False) -> str:
    """Read the routing floor without decrypting transport credentials."""
    row = session.get(Setting, "notification_settings", populate_existing=refresh)
    try:
        config = json.loads(row.value) if row and row.value else {}
    except (TypeError, ValueError):
        return "high"
    value = config.get("immediate_min_severity") if isinstance(config, dict) else None
    return value if value in ("low", "medium", "high", "critical") else "high"


def immediate_delivery_allowed(
    session: Session, alert: Alert, immediate: bool | None = None, *, refresh: bool = False
) -> bool:
    """Recheck current parent policy; a saved queue flag cannot override it."""
    if immediate is False:
        return False
    profile = session.get(ChildProfile, alert.profile_id, populate_existing=refresh) if alert.profile_id else None
    policy = profile_policy.normalize(profile.alert_policy, profile.age_group) if profile else (
        profile_policy.default_policy_for_age("10_13")
    )
    risk = session.get(RiskResult, alert.risk_id, populate_existing=refresh)
    decision = profile_policy.decide(
        policy, alert.severity, risk.categories or [] if risk else [],
        notification_min_severity=immediate_min_severity(session, refresh=refresh),
    )
    return decision.create_alert and decision.notify

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
        sock = self._create_connection((self._connect_host, self.port), self.timeout, self.source_address)  # type: ignore[attr-defined]
        if self._tunnel_host:  # type: ignore[attr-defined]
            self.sock = sock
            self._tunnel()  # type: ignore[attr-defined]
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)  # type: ignore[attr-defined]


def _get_smtp_config(session: Session) -> dict[str, Any] | None:
    if not consent.choice_allowed(session, "notifications"):
        return None
    row = session.get(Setting, "notification_settings", populate_existing=True)
    if not row or not row.value:
        return None
    try:
        cfg = json.loads(row.value)
    except Exception:
        return None
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return None
    enc = cfg.get("password_enc")
    if enc:
        try:
            cfg["password"] = encryption.decrypt_text(base64.b64decode(enc.encode("ascii")))
        except Exception:
            cfg["password"] = ""
    return cfg


def _transport_error(channel: str, error: Exception) -> str:
    """Fixed diagnostics: server exception messages can echo credentials/URLs."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        reason = "authentication rejected"
    elif isinstance(error, (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused)):
        reason = "sender or recipient rejected"
    elif isinstance(error, ssl.SSLCertVerificationError):
        reason = "TLS certificate verification failed"
    elif isinstance(error, ssl.SSLError):
        reason = "TLS negotiation failed"
    elif isinstance(error, TimeoutError):
        reason = "connection timed out"
    elif isinstance(error, socket.gaierror):
        reason = "host could not be resolved"
    elif isinstance(error, OSError):
        reason = "network connection failed"
    else:
        reason = "transport request failed"
    return f"{channel}: {reason}"


def _send_email(cfg: dict[str, Any], subject: str, body: str) -> tuple[bool, str]:
    server: smtplib.SMTP | None = None
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
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if tls_mode == "starttls":
                server.starttls(context=ssl.create_default_context())
        if username and password:
            server.login(username, password)
        server.send_message(msg)
        server.quit()
        return True, "ok"
    except Exception as e:
        detail = _transport_error("SMTP", e)
        log.warning("%s", detail)
        return False, detail
    finally:
        if server is not None:
            try:
                server.close()
            except OSError:
                pass


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
    try:
        parsed = urlparse(url)
    except ValueError:
        return None, "webhook URL is malformed"
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

    The receiver must implement the GuardianNode payload contract. Native push
    services may require an adapter. A parent-configured remote URL sends these
    fields outside the local network; private targets require explicit opt-in.
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
    except Exception as e:
        detail = _transport_error("Webhook", e)
        log.warning("%s", detail)
        return False, detail


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

    Built-in transports return fixed error categories and status codes instead
    of raw exception messages or server response text.
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
    include_dashboard: bool = True,
    skip_channels: set[str] | None = None,
) -> list[NotificationLog]:
    """Dispatch according to current severity, profile, and consent settings."""
    is_immediate = immediate_delivery_allowed(session, alert, immediate, refresh=True)
    skipped = skip_channels or set()
    logs: list[NotificationLog] = []

    # 1) Dashboard — always recorded (the dashboard reads from alerts table)
    if include_dashboard:
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
    if cfg and is_immediate and cfg.get("host") and "email" not in skipped:
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

    # 3) Generic GuardianNode JSON webhook if immediate delivery is eligible.
    # SMTP can block while another parent request changes consent or settings.
    # Each external channel gets a fresh decision immediately before transport.
    cfg = _get_smtp_config(session)
    is_immediate = immediate_delivery_allowed(session, alert, immediate, refresh=True)
    if cfg and is_immediate and cfg.get("webhook_url") and "webhook" not in skipped:
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


def enqueue(
    session: Session,
    *,
    alert: Alert,
    risk_summary: str,
    immediate: bool | None = None,
) -> NotificationJob | None:
    """Record dashboard visibility now and queue external delivery after commit."""
    is_immediate = immediate_delivery_allowed(session, alert, immediate)
    session.add(
        NotificationLog(
            alert_id=alert.alert_id,
            channel="dashboard",
            severity=alert.severity,
            result="ok",
            detail=None,
        )
    )
    if not is_immediate or not consent.effective_policy(session).notifications:
        return None
    job = NotificationJob(
        alert_id=alert.alert_id,
        severity=alert.severity,
        risk_summary=risk_summary,
        immediate=bool(is_immediate),
        status="queued",
        next_attempt_at=datetime.now(UTC),
    )
    session.add(job)
    return job


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _retry_delay_seconds(attempts: int) -> int:
    return (60, 300, 900, 3600)[min(max(attempts - 1, 0), 3)]


def process_pending(session: Session, *, limit: int = 10, now: datetime | None = None) -> int:
    """Deliver queued notification jobs. Returns the number of jobs processed."""
    now = _as_aware_utc(now) or datetime.now(UTC)
    candidates = (
        session.query(NotificationJob)
        .filter(
            NotificationJob.status.in_(["queued", "retry"]),
            or_(NotificationJob.next_attempt_at.is_(None), NotificationJob.next_attempt_at <= now),
        )
        .order_by(NotificationJob.created_at.asc(), NotificationJob.id.asc())
        .limit(limit)
        .all()
    )
    processed = 0
    for job in candidates:
        alert = session.get(Alert, job.alert_id)
        if alert is None:
            job.status = "dead"
            job.last_error = "alert no longer exists"
            job.updated_at = now
            processed += 1
            session.commit()
            continue
        if not immediate_delivery_allowed(session, alert, job.immediate, refresh=True):
            job.status = "skipped"
            job.last_error = POLICY_SUPPRESSED
            job.next_attempt_at = None
            job.updated_at = now
            processed += 1
            session.commit()
            continue
        job.status = "processing"
        job.attempts = int(job.attempts or 0) + 1
        job.updated_at = now
        logs = dispatch(
            session,
            alert=alert,
            risk_summary=job.risk_summary or "",
            immediate=job.immediate,
            include_dashboard=False,
            skip_channels=set(job.delivered_channels or []),
        )
        job.delivered_channels = sorted({
            *(job.delivered_channels or []),
            *(row.channel for row in logs if row.result == "ok"),
        })
        failures = [row for row in logs if row.channel != "dashboard" and row.result != "ok"]
        if failures:
            detail = "; ".join((row.detail or row.channel)[:200] for row in failures)[:500]
            job.last_error = detail
            if job.attempts >= 5:
                job.status = "dead"
                job.next_attempt_at = None
            else:
                job.status = "retry"
                job.next_attempt_at = now + timedelta(seconds=_retry_delay_seconds(job.attempts))
        else:
            job.status = "sent" if job.delivered_channels else "skipped"
            job.last_error = None
            job.next_attempt_at = None
        job.updated_at = now
        processed += 1
        # Persist each outcome independently: a later job failure must not roll
        # back all successful deliveries in this worker batch.
        session.commit()
    return processed
