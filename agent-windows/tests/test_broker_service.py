from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from src.broker_protocol import BrokerRequest, image_to_b64, make_request
from src.broker_service import BrokerCommandHandler, CaptureProcessManager, WindowsNamedPipeServer
from src.pairing_client import save_credentials


class MemoryQueue:
    def __init__(self):
        self.items: list[dict] = []

    def put_nowait(self, payload: dict) -> None:
        self.items.append(payload)

    def qsize(self) -> int:
        return len(self.items)

    def purge(self) -> None:
        self.items.clear()

    def redact_context(self) -> None:
        for item in self.items:
            for key in ("app_name", "window_title", "url", "metadata"):
                item.pop(key, None)


def _handler(tmp_path) -> BrokerCommandHandler:
    return BrokerCommandHandler(
        queue=MemoryQueue(),
        pause_path=tmp_path / "pause_state.json",
        credential_path=tmp_path / "secure" / "device.json",
        legacy_credential_path=tmp_path / "legacy" / "device.json",
        capture_config={"monitoring_enabled": True, "apps_and_urls_enabled": True},
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


def test_broker_returns_only_bounded_capture_config(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.set_capture_config({
        "monitoring_enabled": True,
        "apps_and_urls_enabled": True,
        "level": "balanced",
        "cadence_seconds": 8,
        "phash_threshold": 3,
        "full_screen_change_threshold": 12,
        "max_capture_interval_seconds": 120,
        "full_screen_capture_enabled": True,
        "device_token": "must-not-cross-the-pipe",
    })

    response = handler.handle_message(make_request("capture_config"))

    assert response["ok"]
    assert response["payload"] == {
        "monitoring_enabled": True,
        "apps_and_urls_enabled": True,
        "level": "balanced",
        "cadence_seconds": 8,
        "phash_threshold": 3,
        "full_screen_change_threshold": 12,
        "max_capture_interval_seconds": 120,
        "full_screen_capture_enabled": True,
    }
    assert "must-not-cross-the-pipe" not in json.dumps(response)


def test_parent_pause_reaches_capture_and_blocks_submit(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.set_capture_config({
        "level": "balanced", "cadence_seconds": 5, "paused": True,
        "paused_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "capture_allowed": False,
        "policy_generation": "generation-2", "device_token": "must-not-cross-the-pipe",
    })
    config = handler.handle_message(make_request("capture_config"))["payload"]
    assert config["paused"] is True
    assert config["capture_allowed"] is False
    assert config["policy_generation"] == "generation-2"
    assert handler.applied_policy_generation() == "generation-2"
    assert "device_token" not in config
    assert handler.handle_message(make_request("status"))["payload"]["paused"] is True
    restarted = _handler(tmp_path)
    assert restarted.handle_message(make_request("status"))["payload"]["paused"] is True
    assert restarted.applied_policy_generation() == "generation-2"
    restarted.set_capture_config({"paused": False, "capture_allowed": True})
    assert restarted.handle_message(make_request("status"))["payload"]["paused"] is False


def test_failed_capture_policy_persistence_cannot_ack_generation(tmp_path, monkeypatch) -> None:
    handler = _handler(tmp_path)
    monkeypatch.setattr(Path, "replace", lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    handler.set_capture_config({"capture_allowed": False, "policy_generation": "generation-3"})
    assert handler.applied_policy_generation() is None
    assert handler.handle_message(make_request("capture_config"))["payload"]["capture_allowed"] is False


def test_broker_child_request_uses_owned_token_but_returns_only_dto(tmp_path, monkeypatch) -> None:
    from src import broker_service

    handler = _handler(tmp_path)
    save_credentials("dev-1", "private-device-token", "http://127.0.0.1:8787", handler.credential_path)
    requests = []

    def backend(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer private-device-token"
        return httpx.Response(200, json={
            "request_id": "request-1", "status": "open", "request_type": "more_time",
            "device_id": "dev-1", "device_token": "must-not-return",
        })

    real_client = httpx.Client
    monkeypatch.setattr(
        broker_service.httpx, "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(backend), **kwargs),
    )
    result = handler.handle_request(BrokerRequest(
        action="child_request_create", request_id="ipc-1",
        payload={"request_type": "more_time", "reason": "Synthetic test"},
    ))
    assert result["status"] == "open"
    assert "device_token" not in json.dumps(result)
    assert requests[0].url.path == "/api/child-requests"
def test_parent_capture_boundary_survives_broker_restart(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.set_capture_config({
        "monitoring_enabled": True,
        "apps_and_urls_enabled": True,
        "level": "balanced",
        "full_screen_capture_enabled": False,
        "cadence_seconds": 15,
        "device_token": "must-not-be-persisted",
    })
    assert "must-not-be-persisted" not in handler.capture_config_path.read_text("utf-8")

    restarted = BrokerCommandHandler(
        queue=MemoryQueue(),
        pause_path=tmp_path / "pause_state.json",
        capture_config={"full_screen_capture_enabled": True, "cadence_seconds": 5},
    )
    policy = restarted.handle_message(make_request("capture_config"))["payload"]
    assert policy["full_screen_capture_enabled"] is False
    assert policy["cadence_seconds"] == 15


@pytest.mark.parametrize("cached", ["not json", "[]"])
def test_unreadable_capture_cache_does_not_expand_to_desktop(tmp_path, cached) -> None:
    (tmp_path / "capture_config.json").write_text(cached, encoding="utf-8")
    handler = BrokerCommandHandler(
        queue=MemoryQueue(),
        pause_path=tmp_path / "pause_state.json",
        capture_config={"full_screen_capture_enabled": True, "cadence_seconds": 5},
    )
    assert handler.handle_message(make_request("capture_config"))["payload"]["full_screen_capture_enabled"] is False


@pytest.mark.asyncio
async def test_first_capture_waits_for_parent_broker_policy(monkeypatch) -> None:
    from src import main

    attempts = 0

    class FakeClient:
        def capture_config(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("broker starting")
            return {"monitoring_enabled": True, "full_screen_capture_enabled": False, "cadence_seconds": 15}

    async def immediate_sleep(_seconds):
        return None

    monkeypatch.setattr("src.broker_client.BrokerClient", FakeClient)
    monkeypatch.setattr(main.asyncio, "sleep", immediate_sleep)
    cfg = main.AgentConfig(full_screen_capture_enabled=True)
    await main._initial_broker_capture_config(cfg)

    assert attempts == 2
    assert cfg.full_screen_capture_enabled is False
    assert cfg.ocr_cadence_seconds == 15


@pytest.mark.asyncio
async def test_broker_retries_pending_enrollment_after_startup_outage(tmp_path, monkeypatch) -> None:
    from src import broker_service

    handler = _handler(tmp_path)
    attempts = 0
    sleep_calls = 0

    def fake_bootstrap(_hostname, _version, **kwargs):
        nonlocal attempts
        attempts += 1
        assert kwargs["device_path"] == handler.credential_path
        assert kwargs["attempts"] == 1
        assert kwargs["retry_delay"] == 0.0
        if attempts == 1:
            raise RuntimeError("backend still starting")
        save_credentials("dev-1", "new-token", "http://127.0.0.1:8787", handler.credential_path)

    async def stop_after_recovery(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(broker_service, "bootstrap_pairing", fake_bootstrap)
    monkeypatch.setattr(broker_service.asyncio, "sleep", stop_after_recovery)
    with pytest.raises(asyncio.CancelledError):
        await broker_service._run_pairing_monitor(handler)

    assert attempts == 2, "recovered credentials must stop further bootstrap attempts"
    assert handler.ensure_broker_credentials()["device_token"] == "new-token"


@pytest.mark.asyncio
async def test_broker_upload_refreshes_replaced_enrollment(tmp_path, monkeypatch) -> None:
    from src.backend_client import BackendClient
    from src.broker_service import BrokerBackendClient
    from src.config import AgentConfig

    handler = _handler(tmp_path)
    client = BrokerBackendClient(handler, AgentConfig())
    seen = []

    async def fake_send(self, **_kwargs):
        seen.append((self.base_url, self.token, self.ca_path))
        return {"status": "queued"}

    monkeypatch.setattr(BackendClient, "send_screenshot", fake_send)
    save_credentials("dev-1", "old-token", "http://127.0.0.1:8787", handler.credential_path)
    await client.send_screenshot(image_bytes=b"synthetic")
    save_credentials("dev-2", "new-token", "https://family.test:8787", handler.credential_path, ca_path="new-ca.pem")
    await client.send_screenshot(image_bytes=b"synthetic")

    assert seen == [
        ("http://127.0.0.1:8787", "old-token", None),
        ("https://family.test:8787", "new-token", "new-ca.pem"),
    ]


def test_parent_pause_stops_local_queue_and_survives_restart(tmp_path) -> None:
    handler = _handler(tmp_path)
    until = datetime.now(timezone.utc) + timedelta(hours=1)
    handler.set_capture_config({"monitoring_enabled": True, "paused_until": until.isoformat()})
    restarted = _handler(tmp_path)

    assert restarted.handle_message(make_request("status"))["payload"]["paused"] is True
    response = restarted.handle_message(make_request("submit_screenshot", {
        "image_b64": image_to_b64(b"synthetic paused frame"),
    }))
    assert response["ok"] is True
    assert response["payload"]["status"] == "paused"
    assert restarted.queue.qsize() == 0

    restarted.set_capture_config({"monitoring_enabled": True, "paused_until": None})
    assert restarted.handle_message(make_request("status"))["payload"]["paused"] is False
    response = restarted.handle_message(make_request("submit_screenshot", {
        "image_b64": image_to_b64(b"synthetic resumed frame"),
    }))
    assert response["payload"]["status"] == "queued"
    assert restarted.queue.qsize() == 1


def test_cached_parent_pause_expires_offline_and_uses_utc_for_naive_timestamp(tmp_path) -> None:
    handler = _handler(tmp_path)
    until = datetime.now(timezone.utc) - timedelta(seconds=10)
    handler.set_capture_config({"monitoring_enabled": True, "paused_until": until.replace(tzinfo=None).isoformat()})
    assert _handler(tmp_path).handle_message(make_request("status"))["payload"]["paused"] is False
    assert handler._capture_config["paused_until"].endswith("+00:00")


def test_malformed_server_pause_cannot_clear_current_pause(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.set_capture_config({"monitoring_enabled": True, "paused_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    with pytest.raises(ValueError):
        handler.set_capture_config({"monitoring_enabled": True, "paused_until": "invalid date"})
    assert handler.handle_message(make_request("status"))["payload"]["paused"] is True


def test_broker_requires_server_permission_before_accepting_capture(tmp_path) -> None:
    handler = BrokerCommandHandler(queue=MemoryQueue(), pause_path=tmp_path / "pause_state.json")
    response = handler.handle_message(make_request("submit_screenshot", {
        "image_b64": image_to_b64(b"synthetic unauthorized frame"),
    }))
    assert response["payload"]["status"] == "monitoring_disabled"
    assert handler.queue.qsize() == 0


def test_disabled_monitoring_purges_queue_and_survives_restart(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.queue.put_nowait({"image_bytes": b"pending synthetic frame"})
    handler.set_capture_config({"monitoring_enabled": False})

    assert handler.queue.qsize() == 0
    assert handler.monitoring_enabled is False
    assert _handler(tmp_path).monitoring_enabled is False
    response = handler.handle_message(make_request("submit_screenshot", {
        "image_b64": image_to_b64(b"synthetic disabled frame"),
    }))
    assert response["payload"]["status"] == "monitoring_disabled"


@pytest.mark.asyncio
async def test_disabled_broker_does_not_upload_an_already_claimed_frame(tmp_path, monkeypatch) -> None:
    from src.backend_client import BackendClient
    from src.broker_service import BrokerBackendClient
    from src.config import AgentConfig

    handler = _handler(tmp_path)
    handler.set_capture_config({"monitoring_enabled": False})
    monkeypatch.setattr(BackendClient, "send_screenshot", lambda **_kwargs: pytest.fail("upload attempted"))
    with pytest.raises(RuntimeError, match="monitoring is disabled"):
        await BrokerBackendClient(handler, AgentConfig()).send_screenshot(image_bytes=b"synthetic")


@pytest.mark.asyncio
async def test_context_opt_out_redacts_queue_new_submissions_and_inflight_upload(tmp_path, monkeypatch) -> None:
    from src.backend_client import BackendClient
    from src.broker_service import BrokerBackendClient
    from src.config import AgentConfig

    handler = _handler(tmp_path)
    handler.queue.put_nowait({"image_bytes": b"synthetic", "app_name": "private.exe", "window_title": "private title"})
    save_credentials("dev-1", "synthetic-token", "http://127.0.0.1:8787", handler.credential_path)
    handler.set_capture_config({"monitoring_enabled": True, "apps_and_urls_enabled": False})
    assert "app_name" not in handler.queue.items[0]
    assert "window_title" not in handler.queue.items[0]
    handler.handle_message(make_request("submit_screenshot", {
        "image_b64": image_to_b64(b"synthetic new frame"),
        "app_name": "private.exe", "window_title": "private title",
    }))
    assert "app_name" not in handler.queue.items[1]
    assert "window_title" not in handler.queue.items[1]

    async def fake_send(self, **kwargs):
        assert kwargs.get("app_name") is None
        assert kwargs.get("window_title") is None
        assert kwargs.get("url") is None
        return {"status": "queued"}

    monkeypatch.setattr(BackendClient, "send_screenshot", fake_send)
    await BrokerBackendClient(handler, AgentConfig()).send_screenshot(
        image_bytes=b"claimed before opt-out", app_name="private.exe",
        window_title="private title", url="https://private.example.test",
    )


def test_policy_persistence_failure_cannot_prevent_monitoring_disable(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    handler = _handler(tmp_path)
    handler.set_capture_config({"monitoring_enabled": True, "apps_and_urls_enabled": True})
    handler.queue.put_nowait({"image_bytes": b"synthetic"})

    def failed_replace(self, target):
        raise OSError("synthetic filesystem failure")

    monkeypatch.setattr(Path, "replace", failed_replace)
    handler.set_capture_config({"monitoring_enabled": False, "apps_and_urls_enabled": False})

    assert handler.monitoring_enabled is False
    assert handler.queue.qsize() == 0
    assert not handler.capture_config_path.exists(), "stale permissive policy must not survive restart"


@pytest.mark.asyncio
async def test_enforcement_recovery_failure_does_not_stop_consent_polling(tmp_path, monkeypatch) -> None:
    from src import broker_service
    from src.config import AgentConfig

    handler = _handler(tmp_path)
    save_credentials("dev-1", "synthetic-token", "http://127.0.0.1:8787", handler.credential_path)

    class BrokenEnforcer:
        def reconcile(self):
            raise OSError("synthetic enforcement state unavailable")

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def heartbeat(self, **_kwargs):
            return True

        async def get_capture_config(self):
            return {"monitoring_enabled": False}

        async def get_commands(self):
            return []

    async def stop_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("src.enforcement.WindowsEnforcer", BrokenEnforcer)
    monkeypatch.setattr("src.backend_client.BackendClient", FakeClient)
    monkeypatch.setattr(broker_service.asyncio, "sleep", stop_sleep)
    with pytest.raises(asyncio.CancelledError):
        await broker_service._run_device_control(handler, AgentConfig())
    assert handler.monitoring_enabled is False


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
                "policy_generation": "generation-1",
                "profile_id": "should-not-be-accepted",
                "age_group": "5_7",
            },
        )
    )

    assert response["ok"]
    assert handler.queue.qsize() == 1
    assert handler.queue.items[0]["image_bytes"] == b"jpeg bytes"  # type: ignore[attr-defined]
    assert handler.queue.items[0]["policy_generation"] == "generation-1"  # type: ignore[attr-defined]
    assert "profile_id" not in handler.queue.items[0]  # type: ignore[attr-defined]
    assert "age_group" not in handler.queue.items[0]  # type: ignore[attr-defined]


def test_broker_has_no_password_bearing_actions(tmp_path) -> None:
    handler = _handler(tmp_path)
    for action in ("pause", "resume", "verify_parent"):
        message = make_request("status")
        message["action"] = action
        response = handler.handle_message(message)
        assert not response["ok"]
        assert "unsupported action" in response["error"]


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

    async def fake_capture_config_loop(_cfg):
        await asyncio.Future()

    async def fake_initial_config(_cfg):
        return None

    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr("src.broker_client.BrokerScreenshotQueue", FakeBrokerQueue)
    monkeypatch.setattr(main, "capture_loop", fake_capture_loop)
    monkeypatch.setattr(main, "broker_capture_config_loop", fake_capture_config_loop)
    monkeypatch.setattr(main, "_initial_broker_capture_config", fake_initial_config)
    monkeypatch.setattr(main, "bootstrap_pairing", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(main, "load_credentials", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))

    cfg = main.AgentConfig(dry_run=False, broker_enabled=True)
    try:
        asyncio.run(main.main_async(cfg))
    except asyncio.CancelledError:
        pass


def test_agent_applies_broker_capture_config() -> None:
    from src import main

    cfg = main.AgentConfig()
    main._apply_capture_config(cfg, {
        "cadence_seconds": 15,
        "phash_threshold": 5,
        "full_screen_change_threshold": 18,
        "max_capture_interval_seconds": 300,
        "full_screen_capture_enabled": True,
    })

    assert cfg.ocr_cadence_seconds == 15
    assert cfg.phash_threshold == 5
    assert cfg.full_screen_change_threshold == 18
    assert cfg.max_capture_interval_seconds == 300
    assert cfg.full_screen_capture_enabled is True


def test_named_pipe_identity_validation_uses_win32security_impersonation(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSecurity:
        TokenUser = object()

        @staticmethod
        def ImpersonateNamedPipeClient(_pipe):
            calls.append("impersonate")

        @staticmethod
        def OpenThreadToken(*_args):
            calls.append("open-token")
            return "token"

        @staticmethod
        def GetTokenInformation(_token, _kind):
            return "sid", 0

        @staticmethod
        def ConvertSidToStringSid(_sid):
            return "S-1-5-21-test"

        @staticmethod
        def RevertToSelf():
            calls.append("revert")

    monkeypatch.setitem(__import__("sys").modules, "win32api", SimpleNamespace(GetCurrentThread=lambda: "thread"))
    monkeypatch.setitem(__import__("sys").modules, "win32con", SimpleNamespace(TOKEN_QUERY=1))
    monkeypatch.setitem(
        __import__("sys").modules,
        "win32pipe",
        SimpleNamespace(GetNamedPipeClientProcessId=lambda _pipe: 4242),
    )
    monkeypatch.setitem(__import__("sys").modules, "win32security", FakeSecurity)

    assert WindowsNamedPipeServer._client_pid("pipe") == 4242
    assert calls == ["impersonate", "open-token", "revert"]


def test_named_pipe_server_identifies_client_before_dispatch() -> None:
    source = inspect.getsource(WindowsNamedPipeServer._handle_pipe)

    assert source.index("client_pid = self._client_pid(pipe)") < source.index(
        "self.handler.handle_message(message)"
    )
    assert "self.capture_processes.is_authorized(client_pid)" in source


def test_named_pipe_server_flushes_responses_before_disconnect() -> None:
    source = inspect.getsource(WindowsNamedPipeServer._handle_pipe)

    assert source.count("win32file.FlushFileBuffers(pipe)") >= 1
    assert source.index("win32file.WriteFile(pipe, encode_frame(response))") < source.index(
        "win32file.FlushFileBuffers(pipe)",
        source.index("win32file.WriteFile(pipe, encode_frame(response))"),
    )


def test_capture_process_manager_only_authorizes_tracked_live_pid(monkeypatch, tmp_path) -> None:
    manager = CaptureProcessManager(agent_exe=tmp_path / "GuardianNodeAgent.exe")
    manager._pids_by_session[1] = 4242
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid == 4242)

    assert manager.is_authorized(4242) is True
    assert manager.is_authorized(9999) is False


def test_capture_launch_uses_pywin32_duplicate_token_argument_order(monkeypatch, tmp_path) -> None:
    import sys

    agent = tmp_path / "GuardianNodeAgent.exe"
    agent.write_bytes(b"synthetic executable")
    calls: dict[str, tuple] = {}

    class Handle:
        def Close(self) -> None:
            pass

    class FakeSecurity:
        SecurityImpersonation = 2
        TokenPrimary = 1

        @staticmethod
        def SECURITY_ATTRIBUTES():
            return "security-attributes"

        @staticmethod
        def DuplicateTokenEx(existing, impersonation_level, desired_access, token_type, attributes):
            calls["duplicate"] = (
                existing,
                impersonation_level,
                desired_access,
                token_type,
                attributes,
            )
            return Handle()

    class FakeTs:
        @staticmethod
        def WTSQueryUserToken(session_id):
            calls["session"] = (session_id,)
            return "session-token"

    class FakeProfile:
        @staticmethod
        def CreateEnvironmentBlock(primary, inherit):
            calls["environment"] = (primary, inherit)
            return {"TEST": "1"}

    class FakeProcess:
        class STARTUPINFO:
            pass

        @staticmethod
        def CreateProcessAsUser(*args):
            calls["process"] = args
            return Handle(), Handle(), 4242, 7

    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(
        MAXIMUM_ALLOWED=0x02000000,
        CREATE_UNICODE_ENVIRONMENT=0x00000400,
        CREATE_NO_WINDOW=0x08000000,
    ))
    monkeypatch.setitem(sys.modules, "win32security", FakeSecurity)
    monkeypatch.setitem(sys.modules, "win32ts", FakeTs)
    monkeypatch.setitem(sys.modules, "win32profile", FakeProfile)
    monkeypatch.setitem(sys.modules, "win32process", FakeProcess)

    manager = CaptureProcessManager(agent_exe=agent)

    assert manager._launch_in_session(1) == 4242
    assert calls["duplicate"] == (
        "session-token",
        FakeSecurity.SecurityImpersonation,
        0x02000000,
        FakeSecurity.TokenPrimary,
        "security-attributes",
    )
    assert calls["process"][1] == str(agent)
    assert calls["process"][2] == f'"{agent}" --broker-capture'


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "partial", "persistence_failure"])
async def test_device_control_reports_truthful_partial_results(tmp_path, monkeypatch, outcome) -> None:
    from src import broker_service
    from src.config import AgentConfig
    from src.enforcement import EnforcementStateError

    handler = _handler(tmp_path)
    save_credentials("dev-1", "synthetic-token", "http://127.0.0.1:8787", handler.credential_path)
    result = {
        "suspended_processes": 1,
        "failed_processes": 0 if outcome == "success" else 1,
        "pending_resume_processes": 0,
        "partial_failure": outcome != "success",
        "lease_status": "active",
    }
    reports = []

    class FakeEnforcer:
        def reconcile(self):
            return None

        def execute(self, _command):
            if outcome == "persistence_failure":
                raise EnforcementStateError("synthetic disk error", result=result.copy())
            return result

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def heartbeat(self, **_kwargs):
            return True

        async def get_capture_config(self):
            return None

        async def get_commands(self):
            return [{"command_id": "command-1"}]

        async def report_command(self, command_id, status, detail):
            reports.append((command_id, status, detail))

    async def stop_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("src.enforcement.WindowsEnforcer", FakeEnforcer)
    monkeypatch.setattr("src.backend_client.BackendClient", FakeClient)
    monkeypatch.setattr(broker_service.asyncio, "sleep", stop_sleep)
    with pytest.raises(asyncio.CancelledError):
        await broker_service._run_device_control(handler, AgentConfig())
    assert len(reports) == 1
    command_id, status, detail = reports[0]
    assert command_id == "command-1"
    assert status == ("succeeded" if outcome == "success" else "failed")
    assert detail["suspended_processes"] == 1
    assert detail["lease_status"] == "active"
    assert detail["partial_failure"] is (outcome != "success")
    if outcome == "persistence_failure":
        assert detail["error"] == "synthetic disk error"
