from __future__ import annotations

import asyncio
import multiprocessing
import sqlite3
from pathlib import Path

import httpx
import pytest

from src.durable_queue import DurableScreenshotQueue
from src.main import screenshot_sender_loop


def _construct_queue_process(
    queue_path: str,
    key_path: str,
    barrier,
    results,
) -> None:
    try:
        barrier.wait(timeout=10)
        q = DurableScreenshotQueue(Path(queue_path), key_path=Path(key_path))
        results.put(("ok", q.key_path.read_bytes()))
    except Exception as exc:  # pragma: no cover - exercised in child process
        results.put(("error", repr(exc)))


def _claim_once_process(
    queue_path: str,
    key_path: str,
    barrier,
    results,
) -> None:
    try:
        barrier.wait(timeout=10)
        q = DurableScreenshotQueue(Path(queue_path), key_path=Path(key_path), lease_seconds=30)
        payload = q._get_ready()
        results.put(("ok", None if payload is None else payload.get("app_name")))
    except Exception as exc:  # pragma: no cover - exercised in child process
        results.put(("error", repr(exc)))


def _queue(tmp_path, **kwargs) -> DurableScreenshotQueue:
    return DurableScreenshotQueue(
        tmp_path / "queue.sqlite",
        key_path=tmp_path / "queue.key",
        **kwargs,
    )


def test_durable_queue_encrypts_payload_and_acks(tmp_path):
    q = _queue(tmp_path)
    q.put_nowait({"image_bytes": b"frame", "app_name": "Discord.exe"})

    raw = (tmp_path / "queue.sqlite").read_bytes()
    assert b"Discord.exe" not in raw
    assert b"frame" not in raw

    payload = asyncio.run(q.get())
    assert payload["image_bytes"] == b"frame"
    assert payload["app_name"] == "Discord.exe"
    assert payload["idempotency_key"]
    assert q.qsize() == 1

    q.ack_payload(payload)
    assert q.qsize() == 0


def test_durable_queue_survives_process_restart_and_retry_delay(tmp_path):
    q = _queue(tmp_path)
    q.put_nowait({"image_bytes": b"frame", "app_name": "Browser"})
    payload = asyncio.run(q.get())
    q.retry_payload(payload, delay_seconds=60, error="network down")

    restarted = _queue(tmp_path)
    assert restarted.qsize() == 1
    assert restarted._get_ready() is None

    with sqlite3.connect(tmp_path / "queue.sqlite") as conn:
        conn.execute("UPDATE screenshot_queue SET next_attempt_at = 0")
    recovered = asyncio.run(restarted.get())
    assert recovered["image_bytes"] == b"frame"
    assert recovered["idempotency_key"] == payload["idempotency_key"]


def test_durable_queue_rejects_ack_from_wrong_lease_owner(tmp_path):
    q = _queue(tmp_path)
    q.put_nowait({"image_bytes": b"frame", "app_name": "Browser"})
    payload = asyncio.run(q.get())

    attacker_payload = dict(payload)
    attacker_payload["_queue_lease_owner"] = "not-the-claim-owner"
    _queue(tmp_path).ack_payload(attacker_payload)
    assert q.qsize() == 1

    q.ack_payload(payload)
    assert q.qsize() == 0


def test_durable_queue_recovers_expired_lease(tmp_path):
    q1 = _queue(tmp_path, lease_seconds=30)
    q1.put_nowait({"image_bytes": b"frame", "app_name": "Browser"})
    first = q1._get_ready()
    assert first is not None

    q2 = _queue(tmp_path, lease_seconds=30)
    assert q2._get_ready() is None

    with sqlite3.connect(tmp_path / "queue.sqlite") as conn:
        conn.execute("UPDATE screenshot_queue SET lease_until = 0")

    recovered = q2._get_ready()
    assert recovered is not None
    assert recovered["idempotency_key"] == first["idempotency_key"]
    q2.ack_payload(recovered)
    assert q2.qsize() == 0


def test_durable_queue_enforces_item_cap_by_dropping_oldest(tmp_path):
    q = _queue(tmp_path, max_items=2)
    q.put_nowait({"image_bytes": b"one", "app_name": "One"})
    q.put_nowait({"image_bytes": b"two", "app_name": "Two"})
    q.put_nowait({"image_bytes": b"three", "app_name": "Three"})

    assert q.qsize() == 2
    first = asyncio.run(q.get())
    assert first["app_name"] == "Two"


def test_concurrent_queue_constructors_converge_on_one_key(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(8)
    results = ctx.Queue()
    queue_path = str(tmp_path / "queue.sqlite")
    key_path = str(tmp_path / "queue.key")
    processes = [
        ctx.Process(target=_construct_queue_process, args=(queue_path, key_path, barrier, results))
        for _ in range(8)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)

    assert all(process.exitcode == 0 for process in processes)
    received = [results.get(timeout=1) for _ in processes]
    assert [status for status, _ in received] == ["ok"] * len(processes), received
    keys = {value for _, value in received}
    assert len(keys) == 1
    assert len(next(iter(keys))) == 32


def test_two_processes_cannot_claim_same_item(tmp_path):
    q = _queue(tmp_path, lease_seconds=30)
    q.put_nowait({"image_bytes": b"frame", "app_name": "Browser"})

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    results = ctx.Queue()
    processes = [
        ctx.Process(
            target=_claim_once_process,
            args=(str(tmp_path / "queue.sqlite"), str(tmp_path / "queue.key"), barrier, results),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)

    assert all(process.exitcode == 0 for process in processes)
    received = [results.get(timeout=1) for _ in processes]
    assert [status for status, _ in received] == ["ok", "ok"]
    claimed = [value for _, value in received if value is not None]
    assert claimed == ["Browser"]


class FlakyClient:
    def __init__(self):
        self.calls = 0
        self.idempotency_keys: list[str | None] = []

    async def send_screenshot(self, **kwargs):
        self.calls += 1
        self.idempotency_keys.append(kwargs.get("idempotency_key"))
        if self.calls == 1:
            req = httpx.Request("POST", "http://srv:8787/api/events/screenshot")
            resp = httpx.Response(503, request=req, headers={"Retry-After": "0"})
            raise httpx.HTTPStatusError("busy", request=req, response=resp)
        return {"status": "queued"}


@pytest.mark.asyncio
async def test_sender_retries_durable_queue_until_ack(tmp_path):
    q = _queue(tmp_path)
    q.put_nowait({"image_bytes": b"frame", "app_name": "Game"})
    client = FlakyClient()

    task = asyncio.create_task(screenshot_sender_loop(client, q))
    for _ in range(20):
        if q.qsize() == 0 and client.calls >= 2:
            break
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert q.qsize() == 0
    assert client.calls == 2
    assert client.idempotency_keys[0] == client.idempotency_keys[1]
