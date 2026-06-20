from __future__ import annotations

import httpx
import pytest

from app.services import ollama_client
from app.services.ollama_client import OllamaClient


class _FakeTagsResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"models": [{"name": "llama3.2:1b"}]}


class _FakePullStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def aiter_lines(self):
        yield '{"status":"pulling"}'
        yield '{"status":"success"}'


class _FakeAsyncClient:
    instances = []

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.stream_calls = []
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        self.get_url = url
        return _FakeTagsResponse()

    def stream(self, method, url, json):
        self.stream_calls.append((method, url, json))
        return _FakePullStream()


@pytest.fixture(autouse=True)
def reset_fake_client():
    _FakeAsyncClient.instances.clear()


@pytest.mark.asyncio
async def test_status_uses_finite_status_timeout(monkeypatch):
    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", _FakeAsyncClient)

    status = await OllamaClient(base_url="http://ollama.test", status_timeout=2.5).status()

    assert status.available is True
    assert _FakeAsyncClient.instances[0].timeout == 2.5
    assert _FakeAsyncClient.instances[0].get_url == "http://ollama.test/api/tags"


@pytest.mark.asyncio
async def test_pull_uses_bounded_timeout(monkeypatch):
    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", _FakeAsyncClient)

    await OllamaClient(base_url="http://ollama.test", pull_timeout=123).pull("llama3.2:1b")

    timeout = _FakeAsyncClient.instances[0].timeout
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 30
    assert timeout.read == 123
    assert timeout.write == 30
    assert timeout.pool == 30
    assert _FakeAsyncClient.instances[0].stream_calls == [
        (
            "POST",
            "http://ollama.test/api/pull",
            {"name": "llama3.2:1b", "stream": True},
        )
    ]
