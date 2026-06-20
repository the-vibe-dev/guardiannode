"""Tests for retention cleanup and notification delivery.

Covers two items from the open-source readiness Test Plan:
  - expired alerts/events/blobs/audit rows are removed according to settings;
  - SMTP/webhook test-send records success/failure without leaking secrets.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Alert, AuditLog, Device, Event, EvidenceBlob, NotificationLog, RiskResult
from app.services import notifications, retention


def _old(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _add_alert_chain(session, *, alert_id: str, risk_id: str, severity: str, age_days: int) -> None:
    event_id = f"event-{risk_id}"
    session.flush()
    session.add(Event(event_id=event_id, device_id="d1", source_type="system", timestamp=_old(age_days)))
    session.flush()
    session.add(
        RiskResult(
            risk_id=risk_id,
            event_id=event_id,
            risk_level=severity,
            score=50,
            categories=[],
            summary="test alert",
            evidence=[],
            recommended_action="review",
        )
    )
    session.flush()
    session.add(Alert(alert_id=alert_id, risk_id=risk_id, severity=severity, created_at=_old(age_days)))


def test_run_cleanup_removes_expired_rows(db_session, tmp_path):
    s = db_session
    s.add(Device(device_id="d1", hostname="kid-pc", paired=True))

    # Alerts: an old low-severity (1-day retention) should go; a fresh one stays.
    _add_alert_chain(s, alert_id="a-old", risk_id="r1", severity="low", age_days=10)
    _add_alert_chain(s, alert_id="a-new", risk_id="r2", severity="low", age_days=0)
    # An old critical with 90-day retention but aged 200 days should also go.
    _add_alert_chain(s, alert_id="a-crit-old", risk_id="r3", severity="critical", age_days=200)
    _add_alert_chain(s, alert_id="a-crit-new", risk_id="r4", severity="critical", age_days=5)

    # Orphan event (no RiskResult) older than the low cutoff → removed.
    s.add(Event(event_id="e-orphan", device_id="d1", source_type="browser", timestamp=_old(10)))
    # Recent event stays.
    s.add(Event(event_id="e-recent", device_id="d1", source_type="browser", timestamp=_old(0)))

    # Stale, unreferenced evidence blob with a real file on disk → removed + unlinked.
    blob_path = tmp_path / "stale.bin"
    blob_path.write_bytes(b"ciphertext")
    s.add(
        EvidenceBlob(
            blob_id="b-stale",
            kind="screenshot",
            encrypted_path=str(blob_path),
            size_bytes=10,
            created_at=_old(60),
        )
    )

    # Old + new audit rows.
    s.add(AuditLog(actor="system", action="x", created_at=_old(400)))
    s.add(AuditLog(actor="system", action="y", created_at=_old(1)))
    s.commit()

    deleted = retention.run_cleanup(s, retention.DEFAULT_RETENTION_DAYS)

    ids = {a.alert_id for a in s.query(Alert).all()}
    assert ids == {"a-new", "a-crit-new"}
    assert deleted["alerts"] == 2

    event_ids = {e.event_id for e in s.query(Event).all()}
    assert "e-orphan" not in event_ids
    assert "e-recent" in event_ids

    assert s.query(EvidenceBlob).filter_by(blob_id="b-stale").first() is None
    assert not blob_path.exists()  # file actually unlinked
    assert deleted["blobs"] == 1

    actions = {a.action for a in s.query(AuditLog).all()}
    assert actions == {"y"}
    assert deleted["audit"] == 1


def test_run_cleanup_zero_retention_keeps_severity(db_session):
    """A severity configured with 0 days is skipped (never auto-deleted)."""
    s = db_session
    s.add(Device(device_id="d1", hostname="kid-pc", paired=True))
    _add_alert_chain(s, alert_id="keep", risk_id="r", severity="low", age_days=999)
    s.commit()
    cfg = {**retention.DEFAULT_RETENTION_DAYS, "low": 0}
    retention.run_cleanup(s, cfg)
    assert s.query(Alert).filter_by(alert_id="keep").first() is not None


def test_run_test_records_per_channel_without_leaking_secret(monkeypatch):
    captured = {}

    def fake_email(cfg, subject, body):
        captured["email_password"] = cfg.get("password")
        return True, "ok"

    def fake_webhook(url, payload, **_kwargs):
        captured["webhook_url"] = url
        return False, "connection refused"

    monkeypatch.setattr(notifications, "_send_email", fake_email)
    monkeypatch.setattr(notifications, "_send_webhook", fake_webhook)

    cfg = {
        "enabled": True,
        "host": "smtp.test.invalid",
        "password": "s3cr3t",
        "webhook_url": "http://localhost:1/notify",
        "webhook_allow_private": True,
    }
    results = notifications.run_test(cfg)

    by_channel = {r["channel"]: r for r in results}
    assert by_channel["email"]["ok"] is True
    assert by_channel["webhook"]["ok"] is False
    assert by_channel["webhook"]["detail"] == "connection refused"

    # The secret reached the transport but must never appear in any result detail.
    assert captured["email_password"] == "s3cr3t"
    for r in results:
        assert "s3cr3t" not in (r["detail"] or "")


def test_run_test_no_channels_configured():
    results = notifications.run_test({"enabled": True})
    assert results == [{"channel": "none", "ok": False, "detail": "no channels configured"}]


def test_webhook_validation_rejects_private_dns(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(None, None, None, "", ("192.168.1.10", 443))]

    monkeypatch.setattr(notifications.socket, "getaddrinfo", fake_getaddrinfo)

    ok, detail = notifications._validate_webhook_url("https://notify.example.test/hook")
    assert ok is False
    assert "private/internal" in detail


def test_webhook_validation_rejects_mixed_public_private_dns(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (None, None, None, "", ("93.184.216.34", 443)),
            (None, None, None, "", ("10.0.0.8", 443)),
        ]

    monkeypatch.setattr(notifications.socket, "getaddrinfo", fake_getaddrinfo)

    ok, detail = notifications._validate_webhook_url("https://notify.example.test/hook")
    assert ok is False
    assert "private/internal" in detail


def test_webhook_validation_rejects_userinfo_and_fragment():
    ok, detail = notifications._validate_webhook_url("https://user:pass@example.test/hook")
    assert ok is False
    assert "userinfo" in detail

    ok, detail = notifications._validate_webhook_url("https://example.test/hook#token")
    assert ok is False
    assert "fragment" in detail


def test_webhook_validation_rejects_metadata_host_with_trailing_dot():
    ok, detail = notifications._validate_webhook_url("http://metadata.google.internal./latest", allow_private=True)
    assert ok is False
    assert "metadata" in detail


def test_webhook_validation_allows_public_dns(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(None, None, None, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(notifications.socket, "getaddrinfo", fake_getaddrinfo)

    ok, detail = notifications._validate_webhook_url("https://notify.example.test/hook")
    assert (ok, detail) == (True, "ok")


def test_send_webhook_connects_to_validated_address_with_original_host(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(None, None, None, "", ("93.184.216.34", 80))]

    class FakeResponse:
        status = 204

        def read(self, limit):
            assert limit == 1024
            return b""

    class FakeConnection:
        instances = []

        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.closed = False
            FakeConnection.instances.append(self)

        def request(self, method, path, body=None, headers=None):
            self.method = method
            self.path = path
            self.body = body
            self.headers = headers or {}

        def getresponse(self):
            return FakeResponse()

        def close(self):
            self.closed = True

    monkeypatch.setattr(notifications.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(notifications.http_client, "HTTPConnection", FakeConnection)

    ok, detail = notifications._send_webhook(
        "http://notify.example.test:8080/hook?channel=alerts",
        {"title": "GuardianNode"},
    )

    assert (ok, detail) == (True, "ok")
    conn = FakeConnection.instances[0]
    assert conn.host == "93.184.216.34"
    assert conn.port == 8080
    assert conn.method == "POST"
    assert conn.path == "/hook?channel=alerts"
    assert conn.headers["Host"] == "notify.example.test:8080"
    assert conn.headers["Content-Type"] == "application/json"
    assert conn.closed is True


def test_send_webhook_does_not_follow_redirects(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(None, None, None, "", ("93.184.216.34", 80))]

    def fake_post_webhook(*_args, **_kwargs):
        return 302

    monkeypatch.setattr(notifications.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(notifications, "_post_webhook", fake_post_webhook)

    ok, detail = notifications._send_webhook("http://notify.example.test/hook", {"title": "GuardianNode"})
    assert ok is False
    assert "redirects are not followed" in detail


def test_dispatch_records_dashboard_email_and_webhook(db_session, monkeypatch):
    s = db_session
    monkeypatch.setattr(notifications, "_send_email", lambda cfg, subj, body: (True, "ok"))
    monkeypatch.setattr(notifications, "_send_webhook", lambda url, payload, **_kwargs: (True, "ok"))

    import base64
    import json

    from app.db.models import Setting
    from app.services import encryption

    cfg = {
        "enabled": True,
        "host": "smtp.test.invalid",
        "webhook_url": "http://localhost:1/notify",
        "webhook_allow_private": True,
        "password_enc": base64.b64encode(encryption.encrypt_text("s3cr3t")).decode("ascii"),
    }
    s.add(Setting(key="notification_settings", value=json.dumps(cfg)))
    s.add(Device(device_id="dev1", hostname="kid-pc", paired=True))
    s.flush()
    s.add(Event(event_id="e", device_id="dev1", source_type="system", timestamp=datetime.now(UTC)))
    s.flush()
    s.add(
        RiskResult(
            risk_id="r",
            event_id="e",
            risk_level="critical",
            score=90,
            categories=["grooming"],
            summary="grooming language detected",
            evidence=[],
            recommended_action="review",
        )
    )
    s.flush()
    s.add(Alert(alert_id="al-1", risk_id="r", severity="critical"))
    s.commit()

    alert = s.query(Alert).filter_by(alert_id="al-1").first()
    logs = notifications.dispatch(s, alert=alert, risk_summary="grooming language detected", immediate=True)
    channels = {nl.channel for nl in logs}
    assert channels == {"dashboard", "email", "webhook"}
    assert all(nl.result == "ok" for nl in logs)

    s.flush()
    persisted = s.query(NotificationLog).filter_by(alert_id="al-1").all()
    assert {nl.channel for nl in persisted} == {"dashboard", "email", "webhook"}
    for nl in persisted:
        assert "s3cr3t" not in (nl.detail or "")
