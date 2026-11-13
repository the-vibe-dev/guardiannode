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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from src import __version__
from src.backend_client import BackendClient
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
    def purge(self) -> None: ...
    def redact_context(self) -> None: ...


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
        capture_config: dict[str, Any] | None = None,
        capture_config_path: Path | None = None,
    ):
        self.queue = queue
        self.pause_path = pause_path or broker_pause_path()
        self.credential_path = credential_path or broker_device_path()
        self.legacy_credential_path = legacy_credential_path or default_device_path()
        self.replay_cache = replay_cache or RequestReplayCache()
        self._capture_config_lock = threading.RLock()
        self.capture_config_path = capture_config_path or self.pause_path.with_name("capture_config.json")
        self._capture_config = self._sanitize_capture_config(capture_config or {})
        self._capture_config_persisted = False
        self._persisted_policy_generation: str | None = None
        self._privacy_cleanup_pending = False
        try:
            cached = json.loads(self.capture_config_path.read_text("utf-8"))
            if not isinstance(cached, dict):
                raise ValueError("capture policy must be an object")
            self._capture_config.update(self._sanitize_capture_config(cached))
            self._capture_config_persisted = True
            self._persisted_policy_generation = self._capture_config.get("policy_generation")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # An unreadable previously configured policy must not silently
            # expand the capture boundary back to the whole desktop.
            self._capture_config["full_screen_capture_enabled"] = False
            self._capture_config["monitoring_enabled"] = False
            log.warning("could not load cached capture policy; restricting capture to monitored apps")
        if not self.apps_and_urls_enabled:
            self.queue.redact_context()

    def _server_paused(self) -> bool:
        with self._capture_config_lock:
            config = dict(self._capture_config)
        if config.get("paused") is False:
            return False
        until = config.get("paused_until")
        if isinstance(until, str):
            try:
                return datetime.fromisoformat(until).astimezone(timezone.utc) > datetime.now(timezone.utc)
            except ValueError:
                return True
        return config.get("paused") is True

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
                "monitoring_enabled": self.monitoring_enabled,
                "paused": pause.paused or self._server_paused(),
                "paused_until": pause.paused_until,
            }
        if request.action == "capture_config":
            with self._capture_config_lock:
                return dict(self._capture_config)
        if request.action in {"child_request_create", "child_request_list"}:
            return self._child_request(request.action, request.payload)
        if request.action == "submit_screenshot":
            # One lock spans policy checks, minimization, and insertion so a
            # simultaneous opt-out cannot race an old-context frame into disk.
            with self._capture_config_lock:
                if not self.monitoring_enabled:
                    return {"status": "monitoring_disabled", "queue_depth": self.queue.qsize()}
                if self._load_pause().paused or self._server_paused():
                    return {"status": "paused", "queue_depth": self.queue.qsize()}
                payload = self._screenshot_payload(request.payload)
                self.queue.put_nowait(payload)
                return {"status": "queued", "queue_depth": self.queue.qsize()}
        raise ProtocolError("unsupported action")

    def _child_request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Use broker-owned credentials; return only child-request DTO fields."""
        creds = self._load_credentials()
        token = str(creds.get("device_token") or "")
        if not token:
            raise ProtocolError("device is not paired")
        client = BackendClient(
            str(creds.get("backend_url") or ""), token, ca_path=creds.get("ca_path")
        )
        try:
            with httpx.Client(timeout=5.0, verify=client._verify()) as transport:
                if action == "child_request_create":
                    response = transport.post(
                        f"{client.base_url}/api/child-requests",
                        json=payload,
                        headers=client._headers(),
                    )
                else:
                    response = transport.get(
                        f"{client.base_url}/api/child-requests/mine",
                        headers=client._headers(),
                    )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("child request backend call failed: %s", type(exc).__name__)
            raise ProtocolError("child request could not reach the parent server") from exc
        fields = {
            "request_id", "device_id", "profile_id", "request_type", "target", "reason",
            "status", "response_note", "created_at", "reviewed_at", "expires_at",
        }
        if action == "child_request_create":
            if not isinstance(body, dict):
                raise ProtocolError("invalid child request response")
            return {key: body[key] for key in fields if key in body}
        if not isinstance(body, list) or len(body) > 20 or not all(isinstance(item, dict) for item in body):
            raise ProtocolError("invalid child request list")
        return {"items": [{key: item[key] for key in fields if key in item} for item in body]}

    @staticmethod
    def _sanitize_capture_config(payload: dict[str, Any]) -> dict[str, Any]:
        """Keep only bounded, non-secret capture controls for session agents."""
        clean: dict[str, Any] = {
            "monitoring_enabled": (
                payload.get("monitoring_enabled") is True
                and payload.get("capture_allowed") is not False
            ),
            "apps_and_urls_enabled": payload.get("apps_and_urls_enabled") is True,
        }
        if isinstance(payload.get("paused"), bool):
            clean["paused"] = payload["paused"]
        if isinstance(payload.get("capture_allowed"), bool):
            clean["capture_allowed"] = payload["capture_allowed"]
        generation = payload.get("policy_generation")
        if isinstance(generation, str) and len(generation) <= 64:
            clean["policy_generation"] = generation
        level = payload.get("level")
        if level in {"tight", "balanced", "leeway", "local"}:
            clean["level"] = level
        numeric_bounds = {
            "cadence_seconds": (2, 300),
            "phash_threshold": (0, 256),
            "full_screen_change_threshold": (0, 256),
            "max_capture_interval_seconds": (2, 3600),
        }
        for key, (minimum, maximum) in numeric_bounds.items():
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[key] = max(minimum, min(maximum, int(value)))
        full_screen = payload.get("full_screen_capture_enabled")
        if isinstance(full_screen, bool):
            clean["full_screen_capture_enabled"] = full_screen
        if "paused_until" in payload:
            paused_until = payload["paused_until"]
            if paused_until is None:
                clean["paused_until"] = None
            elif isinstance(paused_until, str):
                # SQLite-backed API timestamps may be naive; its pause
                # contract treats those as UTC, never the child's local time.
                until = datetime.fromisoformat(paused_until)
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                clean["paused_until"] = until.astimezone(timezone.utc).isoformat()
            else:
                raise ValueError("paused_until must be an ISO timestamp or null")
        return clean

    def set_capture_config(self, payload: dict[str, Any]) -> None:
        clean = self._sanitize_capture_config(payload)
        with self._capture_config_lock:
            if (
                clean == self._capture_config
                and self._capture_config_persisted
                and not self._privacy_cleanup_pending
                and self.capture_config_path.exists()
            ):
                return
            # Collection must stop even when the disk cannot save the new
            # choice. Apply memory state first; persistence is not permission.
            self._capture_config = clean
            self._persisted_policy_generation = None
            try:
                self.capture_config_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.capture_config_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(clean, sort_keys=True), encoding="utf-8")
                if os.name != "nt":
                    os.chmod(temporary, 0o600)
                temporary.replace(self.capture_config_path)
                self._capture_config_persisted = True
                self._persisted_policy_generation = clean.get("policy_generation")
            except OSError:
                self._capture_config_persisted = False
                log.warning("could not persist capture policy; applying current server choices in memory")
                # Avoid loading an older permissive cache after restart when
                # replacing it failed (for example, after disk exhaustion).
                try:
                    self.capture_config_path.unlink(missing_ok=True)
                except OSError:
                    log.error("could not remove stale capture policy cache")
            self._privacy_cleanup_pending = True
            if not clean["monitoring_enabled"]:
                self.queue.purge()
            elif not clean["apps_and_urls_enabled"]:
                self.queue.redact_context()
            self._privacy_cleanup_pending = False

    def applied_policy_generation(self) -> str | None:
        with self._capture_config_lock:
            return self._persisted_policy_generation

    @property
    def monitoring_enabled(self) -> bool:
        with self._capture_config_lock:
            return self._capture_config.get("monitoring_enabled") is True

    @property
    def apps_and_urls_enabled(self) -> bool:
        with self._capture_config_lock:
            return self._capture_config.get("apps_and_urls_enabled") is True

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
            "policy_generation",
            "collector_version",
            "timestamp",
            "idempotency_key",
        ):
            value = payload.get(key)
            if value:
                out[key] = value
        if not self.apps_and_urls_enabled:
            for key in ("app_name", "window_title", "url"):
                out.pop(key, None)
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


class BrokerBackendClient(BackendClient):
    """Reload the broker-owned enrollment before each upload attempt."""

    def __init__(self, handler: BrokerCommandHandler, cfg: AgentConfig):
        super().__init__(cfg.backend_url, "")
        self.handler = handler

    async def send_screenshot(self, **kwargs) -> dict:
        if not self.handler.monitoring_enabled:
            raise RuntimeError("monitoring is disabled by the server policy")
        if not self.handler.apps_and_urls_enabled:
            for key in ("app_name", "window_title", "url"):
                kwargs[key] = None
        creds = self.handler.ensure_broker_credentials()
        if not creds.get("device_token"):
            raise RuntimeError("device enrollment is pending")
        self.base_url = str(creds["backend_url"]).rstrip("/")
        self.token = str(creds["device_token"])
        self.ca_path = str(creds.get("ca_path") or "") or None
        return await super().send_screenshot(**kwargs)


async def _run_pairing_monitor(handler: BrokerCommandHandler) -> None:
    """Recover a transient installation-time outage without restarting Windows."""
    while True:
        try:
            if not handler.ensure_broker_credentials().get("device_token"):
                await asyncio.to_thread(
                    bootstrap_pairing,
                    socket.gethostname(),
                    __version__,
                    pending_path=pending_pairing_path(),
                    device_path=handler.credential_path,
                    bootstrap_token_path=broker_bootstrap_token_path(),
                    attempts=1,
                    retry_delay=0.0,
                )
        except Exception as exc:
            log.warning("broker pairing retry failed: %s", exc)
        await asyncio.sleep(30)


async def _run_sender(handler: BrokerCommandHandler, cfg: AgentConfig) -> None:

    while True:
        creds = handler.ensure_broker_credentials()
        token = str(creds.get("device_token") or "")
        if not token or not handler.monitoring_enabled:
            await asyncio.sleep(10)
            continue
        try:
            await screenshot_sender_loop(
                BrokerBackendClient(handler, cfg),
                handler.queue,
            )  # type: ignore[arg-type]
        except Exception as exc:
            log.warning("broker sender restarted after %s", type(exc).__name__)
        await asyncio.sleep(10)


async def _run_device_control(handler: BrokerCommandHandler, cfg: AgentConfig) -> None:
    from src.backend_client import BackendClient
    from src.enforcement import EnforcementStateError, WindowsEnforcer

    enforcer = WindowsEnforcer()
    while True:
        try:
            recovery = enforcer.reconcile()
            if recovery and recovery.get("partial_failure"):
                log.warning(
                    "endpoint recovery incomplete: failed=%s pending_resume=%s legacy_unverified=%s",
                    recovery.get("failed_processes", 0), recovery.get("pending_resume_processes", 0),
                    recovery.get("legacy_unverified_processes", 0),
                )
        except Exception:
            # An action-state/disk error must not kill the policy/heartbeat
            # task, leaving uploads running with an indefinitely stale policy.
            log.exception("could not reconcile endpoint actions; continuing policy polling")
        creds = handler.ensure_broker_credentials()
        token = str(creds.get("device_token") or "")
        if not token:
            await asyncio.sleep(10)
            continue
        if pending_pairing_path().exists():
            try:
                await asyncio.to_thread(
                    bootstrap_pairing,
                    socket.gethostname(),
                    __version__,
                    pending_path=pending_pairing_path(),
                    device_path=handler.credential_path,
                    bootstrap_token_path=broker_bootstrap_token_path(),
                    attempts=1,
                    replace_existing=True,
                )
            except Exception as exc:
                log.warning("broker re-pair retry failed: %s", type(exc).__name__)
            creds = handler.ensure_broker_credentials()
            token = str(creds.get("device_token") or "")
        client = BackendClient(
            str(creds.get("backend_url") or cfg.backend_url),
            token,
            ca_path=creds.get("ca_path"),
        )
        try:
            await client.heartbeat(
                queued_frames=handler.queue.qsize(),
                applied_policy_generation=handler.applied_policy_generation(),
            )
            capture_config = await client.get_capture_config()
            if capture_config:
                handler.set_capture_config(capture_config)
            for command in await client.get_commands():
                command_id = str(command.get("command_id") or "")
                try:
                    if command.get("command_type") in {"pause_app", "block_domain"} and not cfg.enforcement_enabled:
                        raise ValueError("device enforcement is disabled pending Windows qualification")
                    result = enforcer.execute(command)
                    status = "failed" if result.get("partial_failure") else "succeeded"
                    await client.report_command(command_id, status, result)
                except ValueError as exc:
                    await client.report_command(command_id, "rejected", {"error": str(exc)[:500]})
                except EnforcementStateError as exc:
                    log.exception("device command %s has incomplete recovery state", command_id)
                    await client.report_command(command_id, "failed", {**exc.result, "error": str(exc)[:500]})
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
    return BrokerCommandHandler(
        queue=queue,
        capture_config={
            "level": "local",
            "cadence_seconds": cfg.ocr_cadence_seconds,
            "phash_threshold": cfg.phash_threshold,
            "full_screen_change_threshold": cfg.full_screen_change_threshold,
            "max_capture_interval_seconds": cfg.max_capture_interval_seconds,
            "full_screen_capture_enabled": cfg.full_screen_capture_enabled,
        },
    )


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
    if args.self_test:
        log.info("broker self-test ok")
        return
    handler = build_handler(cfg)
    try:
        bootstrap_pairing(
            socket.gethostname(),
            __version__,
            pending_path=pending_pairing_path(),
            device_path=handler.credential_path,
            bootstrap_token_path=broker_bootstrap_token_path(),
            replace_existing=True,
        )
    except Exception as exc:
        log.warning("broker pairing bootstrap failed: %s", exc)
    handler.ensure_broker_credentials()
    if os.name != "nt":
        raise SystemExit("GuardianNode endpoint broker service currently runs only on Windows")

    loop = asyncio.new_event_loop()
    loop.create_task(_run_pairing_monitor(handler))
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
