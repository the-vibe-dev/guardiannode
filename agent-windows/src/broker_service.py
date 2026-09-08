"""GuardianNode endpoint broker service.

The Windows broker is the privileged local owner for device credentials, queue
state, pause state, and backend transport. Interactive session processes should
send bounded capture/status requests to this service rather than reading tokens
or mutating authoritative state directly.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src import __version__
from src.broker_protocol import (
    PIPE_NAME,
    PIPE_SECURITY_SDDL,
    MAX_MESSAGE_BYTES,
    BrokerRequest,
    ProtocolError,
    decode_frame,
    encode_frame,
    image_from_b64,
    make_response,
    parse_request,
)
from src.config import AgentConfig, default_config_path, default_device_path
from src.durable_queue import DurableScreenshotQueue, default_key_path, default_queue_path
from src.main import screenshot_sender_loop
from src.pairing_client import bootstrap_pairing, load_credentials, pending_pairing_path, save_credentials

log = logging.getLogger("guardiannode.broker")

MAX_ACTIVE_REQUEST_IDS = 512
MAX_PIPE_CLIENTS = 8
PIPE_READ_DEADLINE_SECONDS = 5.0


def default_secure_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode" / "Secure"
    return Path.home() / ".guardiannode" / "Secure"


def broker_device_path() -> Path:
    return default_secure_dir() / "device.json"


def broker_pause_path() -> Path:
    return default_secure_dir() / "pause_state.json"


def broker_parent_credentials_path() -> Path:
    return default_secure_dir() / "parent.json"


def broker_bootstrap_token_path() -> Path:
    return default_device_path().parent / "keys" / "device_bootstrap_token.json"


class QueueLike(Protocol):
    def put_nowait(self, payload: dict[str, Any]) -> None: ...
    def qsize(self) -> int: ...


@dataclass
class PauseState:
    paused_until: int = 0
    actor: str = ""

    @property
    def paused(self) -> bool:
        return self.paused_until > int(time.time())


class RequestReplayCache:
    def __init__(self, max_size: int = MAX_ACTIVE_REQUEST_IDS):
        self.max_size = max_size
        self._seen: list[str] = []

    def remember(self, request_id: str) -> bool:
        if request_id in self._seen:
            return False
        self._seen.append(request_id)
        if len(self._seen) > self.max_size:
            self._seen = self._seen[-self.max_size :]
        return True


class BrokerCommandHandler:
    def __init__(
        self,
        *,
        queue: QueueLike,
        pause_path: Path | None = None,
        credential_path: Path | None = None,
        legacy_credential_path: Path | None = None,
        replay_cache: RequestReplayCache | None = None,
    ):
        self.queue = queue
        self.pause_path = pause_path or broker_pause_path()
        self.credential_path = credential_path or broker_device_path()
        self.legacy_credential_path = legacy_credential_path or default_device_path()
        self.replay_cache = replay_cache or RequestReplayCache()

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any]:
        try:
            request = parse_request(message)
            if not self.replay_cache.remember(request.request_id):
                raise ProtocolError("duplicate request_id")
            payload = self.handle_request(request)
            return make_response(request.request_id, ok=True, payload=payload)
        except ProtocolError as exc:
            request_id = message.get("request_id", "") if isinstance(message, dict) else ""
            if not isinstance(request_id, str):
                request_id = ""
            return make_response(request_id, ok=False, error=str(exc))
        except Exception:
            log.exception("broker request failed")
            request_id = message.get("request_id", "") if isinstance(message, dict) else ""
            if not isinstance(request_id, str):
                request_id = ""
            return make_response(request_id, ok=False, error="internal broker error")

    def handle_request(self, request: BrokerRequest) -> dict[str, Any]:
        if request.action == "health":
            return {"status": "ok", "queue_depth": self.queue.qsize()}
        if request.action == "status":
            pause = self._load_pause()
            creds = self._load_credentials()
            return {
                "paired": bool(creds.get("device_token")),
                "device_id": creds.get("device_id") or "",
                "backend_url": creds.get("backend_url") or "",
                "queue_depth": self.queue.qsize(),
                "paused": pause.paused,
                "paused_until": pause.paused_until,
            }
        if request.action == "submit_screenshot":
            payload = self._screenshot_payload(request.payload)
            self.queue.put_nowait(payload)
            return {"status": "queued", "queue_depth": self.queue.qsize()}
        raise ProtocolError("unsupported action")

    def ensure_broker_credentials(self) -> dict[str, Any]:
        creds = load_credentials(self.credential_path)
        if creds and creds.get("device_token"):
            return creds
        legacy = load_credentials(self.legacy_credential_path)
        if legacy and legacy.get("device_token"):
            saved = save_credentials(
                str(legacy["device_id"]),
                str(legacy["device_token"]),
                str(legacy["backend_url"]),
                self.credential_path,
                ca_path=legacy.get("ca_path"),
                ca_sha256=str(legacy.get("ca_sha256") or ""),
            )
            log.info("migrated legacy device credential into broker-owned storage: %s", saved)
            return load_credentials(self.credential_path) or {}
        return {}

    def _load_credentials(self) -> dict[str, Any]:
        return self.ensure_broker_credentials()

    def _screenshot_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        image_bytes = image_from_b64(payload["image_b64"])
        out: dict[str, Any] = {"image_bytes": image_bytes}
        for key in (
            "app_name",
            "window_title",
            "capture_scope",
            "policy_id",
            "policy_version",
            "collector_version",
            "timestamp",
            "idempotency_key",
        ):
            value = payload.get(key)
            if value:
                out[key] = value
        return out

    def _load_pause(self) -> PauseState:
        try:
            data = json.loads(self.pause_path.read_text("utf-8"))
            return PauseState(
                paused_until=int(data.get("paused_until") or 0),
                actor=str(data.get("actor") or ""),
            )
        except Exception:
            return PauseState()

    def _save_pause(self, state: PauseState) -> None:
        self.pause_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pause_path.with_suffix(self.pause_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({"paused_until": state.paused_until, "actor": state.actor}),
            encoding="utf-8",
        )
        if os.name != "nt":
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        tmp.replace(self.pause_path)


class CaptureProcessManager:
    """Launch one capture process in each active Windows session and track its PID."""

    def __init__(self, agent_exe: Path | None = None):
        self.agent_exe = agent_exe or Path(sys.executable).resolve().with_name("GuardianNodeAgent.exe")
        self._pids_by_session: dict[int, int] = {}
        self._lock = threading.Lock()

    def is_authorized(self, pid: int) -> bool:
        with self._lock:
            return pid in self._pids_by_session.values() and self._pid_is_running(pid)

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        try:
            import psutil

            return psutil.pid_exists(pid)
        except Exception:
            return False

    def serve_forever(self) -> None:
        if os.name != "nt":
            return
        while True:
            try:
                self._reconcile_sessions()
            except Exception:
                log.exception("could not reconcile broker-owned capture processes")
            time.sleep(10)

    def _reconcile_sessions(self) -> None:
        import win32ts  # type: ignore

        active_sessions = {
            int(row["SessionId"])
            for row in win32ts.WTSEnumerateSessions(None, 1, 0)
            if row.get("State") == win32ts.WTSActive
        }
        with self._lock:
            for session_id, pid in list(self._pids_by_session.items()):
                if session_id not in active_sessions or not self._pid_is_running(pid):
                    self._pids_by_session.pop(session_id, None)
            missing = active_sessions - self._pids_by_session.keys()
        for session_id in missing:
            pid = self._launch_in_session(session_id)
            with self._lock:
                self._pids_by_session[session_id] = pid
            log.info("launched authorized capture process pid=%d session=%d", pid, session_id)

    def _launch_in_session(self, session_id: int) -> int:
        import win32con  # type: ignore
        import win32process  # type: ignore
        import win32profile  # type: ignore
        import win32security  # type: ignore
        import win32ts  # type: ignore

        if not self.agent_exe.is_file():
            raise RuntimeError(f"capture executable is missing: {self.agent_exe}")
        token_attributes = win32security.SECURITY_ATTRIBUTES()
        primary = win32security.DuplicateTokenEx(
            win32ts.WTSQueryUserToken(session_id),
            win32security.SecurityImpersonation,
            win32con.MAXIMUM_ALLOWED,
            win32security.TokenPrimary,
            token_attributes,
        )
        environment = win32profile.CreateEnvironmentBlock(primary, False)
        startup = win32process.STARTUPINFO()
        process, thread, pid, _tid = win32process.CreateProcessAsUser(
            primary,
            str(self.agent_exe),
            f'"{self.agent_exe}" --broker-capture',
            None,
            None,
            False,
            win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NO_WINDOW,
            environment,
            str(self.agent_exe.parent),
            startup,
        )
        process.Close()
        thread.Close()
        primary.Close()
        return int(pid)


class WindowsNamedPipeServer:
    def __init__(
        self,
        handler: BrokerCommandHandler,
        pipe_name: str = PIPE_NAME,
        capture_processes: CaptureProcessManager | None = None,
    ):
        self.handler = handler
        self.pipe_name = pipe_name
        self.capture_processes = capture_processes or CaptureProcessManager()
        self._slots = threading.BoundedSemaphore(MAX_PIPE_CLIENTS)

    def serve_forever(self) -> None:
        if os.name != "nt":
            raise RuntimeError("named pipe broker is only supported on Windows")
        import win32file  # type: ignore
        import win32pipe  # type: ignore
        import win32security  # type: ignore

        security = win32security.SECURITY_ATTRIBUTES()
        security.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            PIPE_SECURITY_SDDL,
            win32security.SDDL_REVISION_1,
        )
        log.info("GuardianNode endpoint broker listening on %s", self.pipe_name)
        while True:
            pipe = win32pipe.CreateNamedPipe(
                self.pipe_name,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES,
                MAX_MESSAGE_BYTES + 4,
                MAX_MESSAGE_BYTES + 4,
                0,
                security,
            )
            win32pipe.ConnectNamedPipe(pipe, None)
            if not self._slots.acquire(blocking=False):
                win32file.CloseHandle(pipe)
                continue
            threading.Thread(
                target=self._handle_pipe,
                args=(pipe,),
                name="GuardianNodeBrokerClient",
                daemon=True,
            ).start()

    def _handle_pipe(self, pipe) -> None:  # noqa: ANN001
        import pywintypes  # type: ignore
        import win32file  # type: ignore
        import win32pipe  # type: ignore

        try:
            frame = self._read_frame(pipe)
            client_pid = self._client_pid(pipe)
            if client_pid is None:
                response = make_response("", ok=False, error="unauthorized client")
            else:
                message = decode_frame(frame)
                if (
                    message.get("action") == "submit_screenshot"
                    and not self.capture_processes.is_authorized(client_pid)
                ):
                    response = make_response("", ok=False, error="unauthorized capture process")
                else:
                    response = self.handler.handle_message(message)
            win32file.WriteFile(pipe, encode_frame(response))
            win32file.FlushFileBuffers(pipe)
        except (pywintypes.error, ProtocolError) as exc:
            log.warning("named pipe request failed: %s", exc)
        finally:
            try:
                win32pipe.DisconnectNamedPipe(pipe)
            except Exception:
                pass
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass
            self._slots.release()

    @staticmethod
    def _read_frame(pipe) -> bytes:  # noqa: ANN001
        header = WindowsNamedPipeServer._read_exact(pipe, 4)
        size = int.from_bytes(header, "big")
        if size > MAX_MESSAGE_BYTES:
            raise ProtocolError("message too large")
        body = WindowsNamedPipeServer._read_exact(pipe, size)
        return header + body

    @staticmethod
    def _read_exact(pipe, size: int) -> bytes:  # noqa: ANN001
        import win32file  # type: ignore
        import win32pipe  # type: ignore

        deadline = time.monotonic() + PIPE_READ_DEADLINE_SECONDS
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            if time.monotonic() >= deadline:
                raise ProtocolError("pipe read deadline exceeded")
            _peeked, available, _left = win32pipe.PeekNamedPipe(pipe, 0)
            if not available:
                time.sleep(0.01)
                continue
            _status, chunk = win32file.ReadFile(pipe, min(remaining, available))
            if not chunk:
                raise ProtocolError("short frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _client_pid(pipe) -> int | None:  # noqa: ANN001
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32security  # type: ignore

        try:
            win32security.ImpersonateNamedPipeClient(pipe)
            token = win32security.OpenThreadToken(
                win32api.GetCurrentThread(),
                win32con.TOKEN_QUERY,
                True,
            )
            user_sid, _attrs = win32security.GetTokenInformation(token, win32security.TokenUser)
            sid_text = win32security.ConvertSidToStringSid(user_sid)
            import win32pipe  # type: ignore

            pid = int(win32pipe.GetNamedPipeClientProcessId(pipe))
            log.debug("accepted local broker client sid=%s pid=%d", sid_text, pid)
            return pid
        except Exception:
            log.warning("could not validate named pipe client identity", exc_info=True)
            return None
        finally:
            try:
                win32security.RevertToSelf()
            except Exception:
                pass


async def _run_sender(handler: BrokerCommandHandler, cfg: AgentConfig) -> None:
    from src.backend_client import BackendClient

    while True:
        creds = handler.ensure_broker_credentials()
        token = str(creds.get("device_token") or "")
        backend_url = str(creds.get("backend_url") or cfg.backend_url)
        if not token:
            await asyncio.sleep(10)
            continue
        await screenshot_sender_loop(
            BackendClient(backend_url, token, ca_path=creds.get("ca_path")),
            handler.queue,
        )  # type: ignore[arg-type]


async def _run_device_control(handler: BrokerCommandHandler, cfg: AgentConfig) -> None:
    from src.backend_client import BackendClient
    from src.enforcement import WindowsEnforcer

    enforcer = WindowsEnforcer()
    while True:
        enforcer.reconcile()
        creds = handler.ensure_broker_credentials()
        token = str(creds.get("device_token") or "")
        if not token:
            await asyncio.sleep(10)
            continue
        client = BackendClient(
            str(creds.get("backend_url") or cfg.backend_url),
            token,
            ca_path=creds.get("ca_path"),
        )
        try:
            await client.heartbeat(queued_frames=handler.queue.qsize())
            for command in await client.get_commands():
                command_id = str(command.get("command_id") or "")
                try:
                    result = enforcer.execute(command)
                    await client.report_command(command_id, "succeeded", result)
                except ValueError as exc:
                    await client.report_command(command_id, "rejected", {"error": str(exc)[:500]})
                except Exception as exc:
                    log.exception("device command %s failed", command_id)
                    await client.report_command(command_id, "failed", {"error": str(exc)[:500]})
        except Exception as exc:
            log.debug("device control poll failed: %s", exc)
        await asyncio.sleep(10)


def build_handler(cfg: AgentConfig) -> BrokerCommandHandler:
    queue = DurableScreenshotQueue(
        default_queue_path(),
        key_path=default_key_path(),
        max_items=cfg.durable_queue_max_items,
        max_bytes=cfg.durable_queue_max_bytes,
        max_age_seconds=cfg.durable_queue_max_age_seconds,
    )
    return BrokerCommandHandler(queue=queue)


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode endpoint broker service")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--self-test", action="store_true", help="validate broker imports and configuration")
    args = parser.parse_args()

    log_handlers: list[logging.Handler] = []
    if os.name == "nt":
        try:
            from logging.handlers import RotatingFileHandler

            log_path = (
                Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
                / "GuardianNode"
                / "logs"
                / "broker.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            log_handlers.append(file_handler)
        except Exception:
            pass
    try:
        log_handlers.append(logging.StreamHandler())
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=log_handlers or None,
        force=True,
    )
    cfg = AgentConfig.from_path(Path(args.config))
    handler = build_handler(cfg)
    try:
        bootstrap_pairing(
            socket.gethostname(),
            __version__,
            pending_path=pending_pairing_path(),
            device_path=handler.credential_path,
            bootstrap_token_path=broker_bootstrap_token_path(),
        )
    except Exception as exc:
        log.warning("broker pairing bootstrap failed: %s", exc)
    handler.ensure_broker_credentials()
    if args.self_test:
        log.info("broker self-test ok")
        return
    if os.name != "nt":
        raise SystemExit("GuardianNode endpoint broker service currently runs only on Windows")

    loop = asyncio.new_event_loop()
    loop.create_task(_run_sender(handler, cfg))
    loop.create_task(_run_device_control(handler, cfg))
    threading.Thread(target=loop.run_forever, name="GuardianNodeBrokerSender", daemon=True).start()
    capture_processes = CaptureProcessManager()
    threading.Thread(
        target=capture_processes.serve_forever,
        name="GuardianNodeCaptureLauncher",
        daemon=True,
    ).start()
    WindowsNamedPipeServer(handler, capture_processes=capture_processes).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    cli()
