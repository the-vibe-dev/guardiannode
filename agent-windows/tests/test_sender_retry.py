from __future__ import annotations

import asyncio

import httpx
import pytest

from src.main import screenshot_sender_loop


class RejectingClient:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.calls = 0

    async def send_screenshot(self, **_kwargs):
        self.calls += 1
        req = httpx.Request("POST", "http://srv:8787/api/events/screenshot")
        resp = httpx.Response(self.status_code, request=req)
        raise httpx.HTTPStatusError("rejected", request=req, response=resp)


@pytest.mark.asyncio
async def test_sender_discards_permanent_payload_errors():
    q: asyncio.Queue = asyncio.Queue(maxsize=2)
    await q.put({"image_bytes": b"not-an-image", "app_name": "BadApp"})
    client = RejectingClient(413)

    task = asyncio.create_task(screenshot_sender_loop(client, q))
    await asyncio.wait_for(q.join(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.calls == 1
    assert q.empty()
