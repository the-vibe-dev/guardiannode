from __future__ import annotations

import asyncio
import inspect
import json
from types import SimpleNamespace

from src.broker_protocol import image_to_b64, make_request
from src.broker_service import BrokerCommandHandler, CaptureProcessManager, WindowsNamedPipeServer
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


def test_broker_returns_only_bounded_capture_config(tmp_path) -> None:
    handler = _handler(tmp_path)
    handler.set_capture_config({
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
        "level": "balanced",
        "cadence_seconds": 8,
        "phash_threshold": 3,
        "full_screen_change_threshold": 12,
        "max_capture_interval_seconds": 120,
        "full_screen_capture_enabled": True,
    }
    assert "must-not-cross-the-pipe" not in json.dumps(response)


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

    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr("src.broker_client.BrokerScreenshotQueue", FakeBrokerQueue)
    monkeypatch.setattr(main, "capture_loop", fake_capture_loop)
    monkeypatch.setattr(main, "broker_capture_config_loop", fake_capture_config_loop)
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
