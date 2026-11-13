"""Notification delivery must not stall ingestion or lose ready work."""
from __future__ import annotations

import asyncio
import json
import ssl
import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import Alert, Device, Event, NotificationJob, RiskResult, Setting
from app.services import notifications
from app.workers import notification_worker


def _job(db, suffix: str, *, created_at=None, due=None):
    db.merge(Device(device_id="notify-device", hostname="synthetic-pc", paired=True))
    db.flush()
    db.add(Event(event_id=f"event-{suffix}", device_id="notify-device",
                 source_type="system", timestamp=datetime.now(UTC)))
    db.flush()
    db.add(RiskResult(risk_id=f"risk-{suffix}", event_id=f"event-{suffix}",
                      risk_level="high", score=80))
    db.flush()
    alert = Alert(alert_id=f"alert-{suffix}", risk_id=f"risk-{suffix}", severity="high")
    db.add(alert)
    db.flush()
    job = notifications.enqueue(db, alert=alert, risk_summary="synthetic signal", immediate=True)
    if created_at is not None:
        job.created_at = created_at
    if due is not None:
        job.next_attempt_at = due
    db.commit()
    return job


def _configure(db, **values):
    db.add(Setting(key="notification_settings", value=json.dumps({"enabled": True, **values})))
    db.commit()


def test_future_retries_do_not_starve_ready_jobs(db_session, monkeypatch):
    now = datetime.now(UTC)
    _configure(db_session, host="smtp.example.test")
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (sent.append(True) or (True, "ok")))
    for i in range(3):
        job = _job(db_session, f"later-{i}", created_at=now - timedelta(minutes=10 - i),
                   due=now + timedelta(minutes=20))
        job.status = "retry"
        db_session.commit()
    ready = _job(db_session, "ready", due=now - timedelta(seconds=1))

    assert notifications.process_pending(db_session, limit=2, now=now) == 1
    assert db_session.get(NotificationJob, ready.id).status == "sent"
    assert sent == [True]


def test_webhook_only_config_does_not_attempt_smtp(db_session, monkeypatch):
    _configure(db_session, webhook_url="https://notify.example.test/hook")
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (sent.append("email") or (False, "no host")))
    monkeypatch.setattr(notifications, "_send_webhook", lambda *args, **kw: (sent.append("webhook") or (True, "ok")))
    job = _job(db_session, "webhook")

    notifications.process_pending(db_session)

    assert sent == ["webhook"]
    assert job.status == "sent"


def test_retry_does_not_resend_successful_channel(db_session, monkeypatch):
    _configure(db_session, host="smtp.example.test", webhook_url="https://notify.example.test/hook")
    sent = []
    outcomes = iter([(False, "temporary failure"), (True, "ok")])
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (sent.append("email") or (True, "ok")))
    monkeypatch.setattr(notifications, "_send_webhook", lambda *args, **kw: (sent.append("webhook") or next(outcomes)))
    job = _job(db_session, "partial")
    first_run = datetime.now(UTC)
    notifications.process_pending(db_session, now=first_run)
    assert job.status == "retry"

    # Delivery state must survive loading the job again, not only an in-memory flag.
    db_session.expire_all()
    notifications.process_pending(db_session, now=first_run + timedelta(minutes=2))

    assert sent == ["email", "webhook", "webhook"]
    assert job.status == "sent"


def test_unconfigured_delivery_is_not_reported_sent(db_session):
    job = _job(db_session, "unconfigured")
    notifications.process_pending(db_session)
    assert job.status == "skipped"


@pytest.mark.parametrize("tls_mode", ["ssl", "starttls"])
def test_smtp_validates_server_certificate(monkeypatch, tls_mode):
    contexts = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context=None):
            if context is not None:
                contexts.append(context)

        def starttls(self, *, context=None):
            contexts.append(context)

        def send_message(self, message):
            assert "synthetic" in message.get_content()

        def quit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", FakeSMTP)
    assert notifications._send_email(
        {"host": "smtp.example.test", "tls_mode": tls_mode}, "Test", "synthetic body"
    )[0]
    assert len(contexts) == 1
    assert contexts[0] is not None
    assert contexts[0].check_hostname is True
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
async def test_notification_transport_runs_off_event_loop(monkeypatch):
    execution_threads = []
    started = threading.Event()

    def run_once():
        execution_threads.append(threading.get_ident())
        started.set()
        return 0

    monkeypatch.setattr(notification_worker, "run_once", run_once)
    task = asyncio.create_task(notification_worker.loop())
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert execution_threads[0] != threading.get_ident()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
