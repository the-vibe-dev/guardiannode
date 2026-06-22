from __future__ import annotations

import asyncio
import json

from src.broker_protocol import image_to_b64, make_request
from src.broker_service import BrokerCommandHandler
from src.pairing_client import save_credentials


class MemoryQueue:
    def __init__(self):
        self.items: list[dict] = []

    def put_nowait(self, payload: dict) -> None:
        self.items.append(payload)

    def qsize(self) -> int:
        return len(self.items)


def _handler(tmp_path) -> BrokerCommandHandler:
    return BrokerCommandHandler(
        queue=MemoryQueue(),
        pause_path=tmp_path / "pause_state.json",
        credential_path=tmp_path / "secure" / "device.json",
        legacy_credential_path=tmp_path / "legacy" / "device.json",
    )


def test_broker_status_never_returns_device_token(tmp_path) -> None:
    handler = _handler(tmp_path)
    save_credentials("dev-1", "secret-token", "http://127.0.0.1:8787", handler.credential_path)

    response = handler.handle_message(make_request("status"))

    assert response["ok"]
    assert response["payload"]["paired"] is True
    assert response["payload"]["device_id"] == "dev-1"
    serialized = json.dumps(response)
    assert "secret-token" not in serialized
    assert "device_token" not in serialized


def test_broker_migrates_legacy_credentials_to_secure_path(tmp_path) -> None:
    handler = _handler(tmp_path)
    save_credentials("dev-1", "secret-token", "http://127.0.0.1:8787", handler.legacy_credential_path)

    creds = handler.ensure_broker_credentials()

    assert creds["device_token"] == "secret-token"
    assert handler.credential_path.exists()


def test_broker_queues_screenshot_without_profile_authority(tmp_path) -> None:
    handler = _handler(tmp_path)
    response = handler.handle_message(
        make_request(
            "submit_screenshot",
            {
                "image_b64": image_to_b64(b"jpeg bytes"),
                "app_name": "Browser",
                "profile_id": "should-not-be-accepted",
                "age_group": "5_7",
            },
        )
    )

    assert response["ok"]
    assert handler.queue.qsize() == 1
    assert handler.queue.items[0]["image_bytes"] == b"jpeg bytes"  # type: ignore[attr-defined]
    assert "profile_id" not in handler.queue.items[0]  # type: ignore[attr-defined]
    assert "age_group" not in handler.queue.items[0]  # type: ignore[attr-defined]


def test_broker_pause_resume_state_is_authoritative(tmp_path) -> None:
    handler = _handler(tmp_path)
    pause = handler.handle_message(make_request("pause", {"duration_seconds": 60, "actor": "test"}))
    status = handler.handle_message(make_request("status"))
    resume = handler.handle_message(make_request("resume", {"actor": "test"}))
    resumed_status = handler.handle_message(make_request("status"))

    assert pause["ok"]
    assert status["payload"]["paused"] is True
    assert resume["ok"]
    assert resumed_status["payload"]["paused"] is False


def test_broker_rejects_replayed_request_id(tmp_path) -> None:
    handler = _handler(tmp_path)
    request = make_request("health")

    first = handler.handle_message(request)
    second = handler.handle_message(request)

    assert first["ok"]
    assert not second["ok"]
    assert "duplicate request_id" in second["error"]


def test_broker_client_queue_submits_to_client() -> None:
    from src.broker_client import BrokerScreenshotQueue

    class FakeClient:
        def __init__(self):
            self.payloads: list[dict] = []

        def submit_screenshot(self, payload: dict) -> dict:
            self.payloads.append(payload)
            return {"status": "queued"}

        def status(self) -> dict:
            return {"queue_depth": len(self.payloads)}

    client = FakeClient()
    queue = BrokerScreenshotQueue(client)  # type: ignore[arg-type]

    queue.put_nowait({"image_bytes": b"frame", "app_name": "Browser"})

    assert queue.qsize() == 1
    assert client.payloads[0]["image_bytes"] == b"frame"


def test_agent_broker_mode_does_not_load_credentials_or_sender(monkeypatch) -> None:
    from src import main

    class FakeBrokerQueue:
        def __init__(self):
            pass

    async def fake_capture_loop(_cfg, queue):
        assert isinstance(queue, FakeBrokerQueue)
        raise asyncio.CancelledError

    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr("src.broker_client.BrokerScreenshotQueue", FakeBrokerQueue)
    monkeypatch.setattr(main, "capture_loop", fake_capture_loop)
    monkeypatch.setattr(main, "bootstrap_pairing", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(main, "load_credentials", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))

    cfg = main.AgentConfig(dry_run=False, broker_enabled=True)
    try:
        asyncio.run(main.main_async(cfg))
    except asyncio.CancelledError:
        pass
