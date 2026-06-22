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
from src.parent_auth import _credentials_path as legacy_parent_credentials_path
from src.parent_auth import verify_password

log = logging.getLogger("guardiannode.broker")

MAX_ACTIVE_REQUEST_IDS = 512


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
        parent_credential_path: Path | None = None,
        legacy_parent_credential_path: Path | None = None,
        replay_cache: RequestReplayCache | None = None,
    ):
        self.queue = queue
        self.pause_path = pause_path or broker_pause_path()
        self.credential_path = credential_path or broker_device_path()
        self.legacy_credential_path = legacy_credential_path or default_device_path()
        self.parent_credential_path = parent_credential_path or broker_parent_credentials_path()
        self.legacy_parent_credential_path = legacy_parent_credential_path or legacy_parent_credentials_path()
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
        if request.action == "pause":
            self._require_parent_password(request.payload)
            until = int(time.time()) + int(request.payload["duration_seconds"])
            actor = str(request.payload.get("actor") or "local-parent")[:128]
            self._save_pause(PauseState(paused_until=until, actor=actor))
            return {"paused": True, "paused_until": until}
        if request.action == "resume":
            self._require_parent_password(request.payload)
            self._save_pause(PauseState())
            return {"paused": False, "paused_until": 0}
        if request.action == "verify_parent":
            self._require_parent_password(request.payload)
            return {"verified": True}
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

    def _require_parent_password(self, payload: dict[str, Any]) -> None:
        password = str(payload.get("parent_password") or "")
        if verify_password(password, self.parent_credential_path):
            return
        if verify_password(password, self.legacy_parent_credential_path):
            return
        raise ProtocolError("parent verification failed")

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


class WindowsNamedPipeServer:
    def __init__(self, handler: BrokerCommandHandler, pipe_name: str = PIPE_NAME):
        self.handler = handler
        self.pipe_name = pipe_name

    def serve_forever(self) -> None:
        if os.name != "nt":
            raise RuntimeError("named pipe broker is only supported on Windows")
        import pywintypes  # type: ignore
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
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
                frame = self._read_frame(pipe)
                if not self._validate_client_identity(pipe):
                    win32file.WriteFile(pipe, encode_frame(make_response("", ok=False, error="unauthorized client")))
                    win32file.FlushFileBuffers(pipe)
                    continue
                response = self.handler.handle_message(decode_frame(frame))
                win32file.WriteFile(pipe, encode_frame(response))
                win32file.FlushFileBuffers(pipe)
            except pywintypes.error as exc:
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

    @staticmethod
    def _read_frame(pipe) -> bytes:  # noqa: ANN001
        import win32file  # type: ignore

        _, header = win32file.ReadFile(pipe, 4)
        size = int.from_bytes(header, "big")
        if size > MAX_MESSAGE_BYTES:
            raise ProtocolError("message too large")
        _, body = win32file.ReadFile(pipe, size)
        return header + body

    @staticmethod
    def _validate_client_identity(pipe) -> bool:  # noqa: ANN001
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
            log.debug("accepted local broker client sid=%s", sid_text)
            return True
        except Exception:
            log.warning("could not validate named pipe client identity", exc_info=True)
            return False
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
        await screenshot_sender_loop(BackendClient(backend_url, token), handler.queue)  # type: ignore[arg-type]


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

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
    threading.Thread(target=loop.run_forever, name="GuardianNodeBrokerSender", daemon=True).start()
    WindowsNamedPipeServer(handler).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    cli()
