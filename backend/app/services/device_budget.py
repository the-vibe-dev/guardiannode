"""Per-device request and byte budgets for ingest fairness."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    requests_per_minute: int
    request_burst: int
    bytes_per_minute: int | None = None


BUDGETS = {
    "heartbeat": Budget(6, 3),
    "screenshot": Budget(12, 4, 64 * 1024 * 1024),
    "text": Budget(120, 30, 10 * 1024 * 1024),
    "child_request": Budget(3, 3),
    "command_poll": Budget(12, 4),
}


class BudgetExceededError(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(f"device budget exceeded; retry in {self.retry_after}s")


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


_buckets: dict[tuple[str, str, str], _Bucket] = {}
_lock = threading.Lock()


def _take(
    key: tuple[str, str, str], *, capacity: float, refill_per_second: float, amount: float
) -> int | None:
    now = time.monotonic()
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = _Bucket(tokens=capacity, updated_at=now)
        _buckets[key] = bucket
    elapsed = max(0.0, now - bucket.updated_at)
    bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_per_second)
    bucket.updated_at = now
    if bucket.tokens >= amount:
        bucket.tokens -= amount
        return None
    missing = amount - bucket.tokens
    return math.ceil(missing / refill_per_second)


def consume(device_id: str, operation: str, body_bytes: int = 0) -> None:
    budget = BUDGETS[operation]
    with _lock:
        retry = _take(
            (device_id, operation, "requests"),
            capacity=float(budget.request_burst),
            refill_per_second=budget.requests_per_minute / 60.0,
            amount=1.0,
        )
        if retry is not None:
            raise BudgetExceededError(retry)
        if budget.bytes_per_minute is not None and body_bytes > 0:
            byte_retry = _take(
                (device_id, operation, "bytes"),
                capacity=float(budget.bytes_per_minute),
                refill_per_second=budget.bytes_per_minute / 60.0,
                amount=float(body_bytes),
            )
            if byte_retry is not None:
                # Refund the request token when byte admission fails.
                request_bucket = _buckets[(device_id, operation, "requests")]
                request_bucket.tokens = min(
                    float(budget.request_burst), request_bucket.tokens + 1.0
                )
                raise BudgetExceededError(byte_retry)


def operation_for_path(path: str, method: str) -> str | None:
    if path == "/api/devices/heartbeat":
        return "heartbeat"
    if path == "/api/events/screenshot":
        return "screenshot"
    if path == "/api/events":
        return "text"
    if path == "/api/child-requests" and method == "POST":
        return "child_request"
    if path == "/api/devices/commands" and method == "GET":
        return "command_poll"
    return None


def clear_for_tests() -> None:
    with _lock:
        _buckets.clear()
