"""Versioned local IPC protocol for the GuardianNode endpoint broker."""
from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

PROTOCOL_VERSION = 1
PIPE_NAME = r"\\.\pipe\GuardianNodeEndpointService"
PIPE_SECURITY_SDDL = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)"
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 1024 * 1024
MAX_STRING_BYTES = 4096
MAX_REQUEST_ID_BYTES = 80

ALLOWED_ACTIONS = {
    "health",
    "status",
    "submit_screenshot",
    "pause",
    "resume",
    "verify_parent",
}


class ProtocolError(ValueError):
    """Raised when a local IPC message is malformed or unsupported."""


@dataclass(frozen=True)
class BrokerRequest:
    action: str
    request_id: str
    payload: dict[str, Any]


def new_request_id() -> str:
    return uuid4().hex


def encode_frame(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    return struct.pack(">I", len(body)) + body


def decode_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < 4:
        raise ProtocolError("short frame")
    size = struct.unpack(">I", frame[:4])[0]
    if size > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    if len(frame) - 4 != size:
        raise ProtocolError("frame length mismatch")
    try:
        message = json.loads(frame[4:].decode("utf-8"))
    except Exception as exc:
        raise ProtocolError("invalid json") from exc
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    return message


def parse_request(message: dict[str, Any]) -> BrokerRequest:
    version = message.get("version")
    if version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    action = message.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ProtocolError("unsupported action")
    request_id = message.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError("request_id is required")
    _bound_string("request_id", request_id, MAX_REQUEST_ID_BYTES)
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    _validate_payload(action, payload)
    return BrokerRequest(action=action, request_id=request_id, payload=payload)


def make_request(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "action": action,
        "request_id": new_request_id(),
        "payload": payload or {},
    }


def make_response(request_id: str, *, ok: bool, payload: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    response: dict[str, Any] = {
        "version": PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": ok,
        "payload": payload or {},
    }
    if error:
        response["error"] = error[:MAX_STRING_BYTES]
    return response


def image_to_b64(image_bytes: bytes) -> str:
    if len(image_bytes) > MAX_SCREENSHOT_BYTES:
        raise ProtocolError("screenshot too large")
    return base64.b64encode(image_bytes).decode("ascii")


def image_from_b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ProtocolError("image_b64 is required")
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise ProtocolError("invalid image_b64") from exc
    if not data:
        raise ProtocolError("image is empty")
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise ProtocolError("screenshot too large")
    return data


def _validate_payload(action: str, payload: dict[str, Any]) -> None:
    if action == "submit_screenshot":
        image_from_b64(payload.get("image_b64"))
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
            if value is not None:
                if not isinstance(value, str):
                    raise ProtocolError(f"{key} must be a string")
                _bound_string(key, value, MAX_STRING_BYTES)
        return
    if action in {"pause", "resume", "verify_parent"}:
        actor = payload.get("actor", "")
        if actor is not None:
            if not isinstance(actor, str):
                raise ProtocolError("actor must be a string")
            _bound_string("actor", actor, MAX_STRING_BYTES)
        parent_password = payload.get("parent_password")
        if not isinstance(parent_password, str) or not parent_password:
            raise ProtocolError("parent_password is required")
        _bound_string("parent_password", parent_password, MAX_STRING_BYTES)
        duration = payload.get("duration_seconds")
        if action == "pause":
            if not isinstance(duration, int) or duration <= 0:
                raise ProtocolError("duration_seconds must be a positive integer")
            if duration > 24 * 60 * 60:
                raise ProtocolError("duration_seconds exceeds maximum")
        return
    if payload:
        for key, value in payload.items():
            if not isinstance(key, str):
                raise ProtocolError("payload keys must be strings")
            if isinstance(value, str):
                _bound_string(key, value, MAX_STRING_BYTES)
            elif not isinstance(value, (bool, int, float, type(None))):
                raise ProtocolError(f"{key} has unsupported type")


def _bound_string(name: str, value: str, limit: int) -> None:
    if len(value.encode("utf-8")) > limit:
        raise ProtocolError(f"{name} too long")
