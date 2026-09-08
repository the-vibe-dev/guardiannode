"""Early ASGI request-body limits applied before parsing and authentication."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

JSON_LIMIT = 256 * 1024
SMALL_DEVICE_LIMIT = 32 * 1024
SCREENSHOT_MULTIPART_LIMIT = 9 * 1024 * 1024


class RequestBodyTooLargeError(Exception):
    pass


def limit_for(path: str) -> int:
    if path == "/api/events/screenshot":
        return SCREENSHOT_MULTIPART_LIMIT
    if path == "/api/events":
        return JSON_LIMIT
    if path.startswith("/api/devices/") or path == "/api/child-requests":
        return SMALL_DEVICE_LIMIT
    return JSON_LIMIT


class RequestBodyLimitMiddleware:
    """Reject large bodies while ASGI chunks arrive, before framework buffering."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or scope.get("method") not in {
            "POST", "PUT", "PATCH", "DELETE"
        }:
            await self.app(scope, receive, send)
            return

        limit = limit_for(str(scope.get("path") or ""))
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._reject(send, 400, b'Bad Request')
                return
            if declared < 0:
                await self._reject(send, 400, b'Bad Request')
                return
            if declared > limit:
                await self._reject(send, 413, b'Request body too large')
                return

        received = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                scope.setdefault("state", {})["request_body_bytes"] = received
                if received > limit:
                    raise RequestBodyTooLargeError
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLargeError:
            if not response_started:
                await self._reject(send, 413, b'Request body too large')

    @staticmethod
    async def _reject(
        send: Callable[[dict[str, Any]], Awaitable[None]], status: int, body: bytes
    ) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
