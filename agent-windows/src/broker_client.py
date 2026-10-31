"""Client helpers for the GuardianNode endpoint broker."""
from __future__ import annotations

import os
import time
from typing import Any

from src.broker_protocol import (
    MAX_MESSAGE_BYTES,
    PIPE_NAME,
    PROTOCOL_VERSION,
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

        request = make_request(action, payload)
        frame = encode_frame(request)
        try:
            win32pipe.WaitNamedPipe(self.pipe_name, self.timeout_ms)
            handle = win32file.CreateFile(
                self.pipe_name,
                0x00120003,  # SYNCHRONIZE | READ_CONTROL | read/write data, not pipe-instance creation
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except Exception as exc:
            raise BrokerUnavailable(str(exc)) from exc
        try:
            self._verify_broker_owner(handle)
            win32file.WriteFile(handle, frame)
            response = self._read_response(handle, request["request_id"])
        finally:
            win32file.CloseHandle(handle)
        if not response.get("ok"):
            raise ProtocolError(str(response.get("error") or "broker request failed"))
        payload_obj = response.get("payload", {})
        if not isinstance(payload_obj, dict):
            raise ProtocolError("broker returned invalid payload")
        return payload_obj

    @staticmethod
    def _verify_broker_owner(handle) -> None:  # noqa: ANN001
        import win32security  # type: ignore

        owner, _group, _dacl, _sacl, _descriptor = win32security.GetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION,
        )
        if win32security.ConvertSidToStringSid(owner) != "S-1-5-18":
            raise BrokerUnavailable("local broker pipe is not owned by SYSTEM")

    @staticmethod
    def _read_exact(handle, size: int) -> bytes:  # noqa: ANN001
        import win32file  # type: ignore
        import win32pipe  # type: ignore

        data = bytearray()
        deadline = time.monotonic() + 5.0
        while len(data) < size:
            if time.monotonic() >= deadline:
                raise BrokerUnavailable("broker response deadline exceeded")
            _peeked, available, _left = win32pipe.PeekNamedPipe(handle, 0)
            if not available:
                time.sleep(0.01)
                continue
            _, chunk = win32file.ReadFile(handle, min(size - len(data), available))
            if not chunk:
                raise ProtocolError("broker disconnected during response")
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _read_response(handle, request_id: str) -> dict[str, Any]:  # noqa: ANN001
        header = BrokerClient._read_exact(handle, 4)
        size = int.from_bytes(header, "big")
        if size > MAX_MESSAGE_BYTES:
            raise ProtocolError("broker response too large")
        body = BrokerClient._read_exact(handle, size)
        response = decode_frame(header + body)
        if response.get("version") != PROTOCOL_VERSION:
            raise ProtocolError("unsupported broker protocol version")
        if response.get("request_id") != request_id:
            raise ProtocolError("broker response request_id mismatch")
        if not isinstance(response.get("ok"), bool):
            raise ProtocolError("broker returned invalid response")
        return response

    def health(self) -> dict[str, Any]:
        return self.request("health")

    def status(self) -> dict[str, Any]:
        return self.request("status")

    def capture_config(self) -> dict[str, Any]:
        return self.request("capture_config")

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
            "policy_generation",
            "collector_version",
            "timestamp",
            "idempotency_key",
        ):
            value = payload.get(key)
            if value:
                broker_payload[key] = value
        return self.request("submit_screenshot", broker_payload)

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
