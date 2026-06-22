"""Client helpers for the GuardianNode endpoint broker."""
from __future__ import annotations

import os
from typing import Any

from src.broker_protocol import (
    PIPE_NAME,
    ProtocolError,
    decode_frame,
    encode_frame,
    image_to_b64,
    make_request,
)


class BrokerUnavailable(RuntimeError):
    """Raised when the local endpoint broker is not reachable."""


class BrokerClient:
    def __init__(self, pipe_name: str = PIPE_NAME, timeout_ms: int = 5000):
        self.pipe_name = pipe_name
        self.timeout_ms = timeout_ms

    def request(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if os.name != "nt":
            raise BrokerUnavailable("broker IPC is only available on Windows")
        import win32file  # type: ignore
        import win32pipe  # type: ignore

        frame = encode_frame(make_request(action, payload))
        try:
            win32pipe.WaitNamedPipe(self.pipe_name, self.timeout_ms)
            handle = win32file.CreateFile(
                self.pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except Exception as exc:
            raise BrokerUnavailable(str(exc)) from exc
        try:
            win32file.WriteFile(handle, frame)
            response = self._read_response(handle)
        finally:
            win32file.CloseHandle(handle)
        if not response.get("ok"):
            raise ProtocolError(str(response.get("error") or "broker request failed"))
        payload_obj = response.get("payload", {})
        if not isinstance(payload_obj, dict):
            raise ProtocolError("broker returned invalid payload")
        return payload_obj

    @staticmethod
    def _read_response(handle) -> dict[str, Any]:  # noqa: ANN001
        import win32file  # type: ignore

        _, header = win32file.ReadFile(handle, 4)
        size = int.from_bytes(header, "big")
        _, body = win32file.ReadFile(handle, size)
        return decode_frame(header + body)

    def health(self) -> dict[str, Any]:
        return self.request("health")

    def status(self) -> dict[str, Any]:
        return self.request("status")

    def submit_screenshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        image_bytes = payload.get("image_bytes")
        if not isinstance(image_bytes, bytes):
            raise ProtocolError("image_bytes is required")
        broker_payload: dict[str, Any] = {"image_b64": image_to_b64(image_bytes)}
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
                broker_payload[key] = value
        return self.request("submit_screenshot", broker_payload)

    def pause(self, duration_seconds: int, *, actor: str = "local-parent") -> dict[str, Any]:
        return self.request("pause", {"duration_seconds": duration_seconds, "actor": actor})

    def resume(self, *, actor: str = "local-parent") -> dict[str, Any]:
        return self.request("resume", {"actor": actor})


class BrokerScreenshotQueue:
    """asyncio.Queue-compatible capture sink backed by the endpoint broker."""

    def __init__(self, client: BrokerClient | None = None):
        self.client = client or BrokerClient()

    def put_nowait(self, payload: dict[str, Any]) -> None:
        self.client.submit_screenshot(payload)

    def qsize(self) -> int:
        try:
            value = self.client.status().get("queue_depth", 0)
            return int(value)
        except Exception:
            return 0

    def full(self) -> bool:
        return False

    async def get(self) -> dict[str, Any]:
        raise BrokerUnavailable("broker queue is write-only from the session agent")

    def task_done(self) -> None:
        return None
