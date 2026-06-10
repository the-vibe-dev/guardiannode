"""Notification routing.

Channels: dashboard (always recorded), email via SMTP (parent-configured), and a
generic webhook that is compatible with self-hosted/local push services such as
ntfy and Gotify (both accept a JSON POST). Every delivery attempt — success or
failure — is recorded as a NotificationLog row so the Audit page can show a
delivery trail without leaking credentials.
"""
from __future__ import annotations

import json
import logging
import smtplib
import base64
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

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


def _send_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """POST a JSON payload to a generic webhook URL.

    The body uses common field names (``title``/``message``/``priority``) so the
    same call works against ntfy, Gotify, and most generic webhook receivers
    without per-service adapters. Local-only by design: no third-party SaaS.
    """
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "GuardianNode"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - parent-supplied URL
            status = getattr(resp, "status", 200)
        if 200 <= int(status) < 300:
            return True, "ok"
        return False, f"webhook returned HTTP {status}"
    except urllib.error.HTTPError as e:  # pragma: no cover - needs a live endpoint
        return False, f"webhook returned HTTP {e.code}"
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
            f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
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
                "time": datetime.now(timezone.utc).isoformat(),
            },
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
