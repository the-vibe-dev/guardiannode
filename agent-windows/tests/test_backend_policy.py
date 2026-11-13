from __future__ import annotations

import httpx
import pytest

from src.backend_client import BackendClient


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_enrollment_disables_monitoring(monkeypatch, status):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, request=request))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))

    policy = await BackendClient("http://127.0.0.1:8787", "synthetic-token").get_capture_config()
    assert policy == {"monitoring_enabled": False}


@pytest.mark.asyncio
async def test_network_outage_preserves_last_known_policy(monkeypatch):
    original = httpx.AsyncClient

    def offline(request):
        raise httpx.ConnectError("synthetic offline backend", request=request)

    transport = httpx.MockTransport(offline)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    assert await BackendClient("http://127.0.0.1:8787", "synthetic-token").get_capture_config() is None
