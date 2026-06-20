"""In-memory sliding-window rate limiter for authentication endpoints.

Protects /auth/login, /auth/recovery-reset, and /devices/pair/complete from
brute-force attempts. State is per-process and resets on backend restart —
acceptable for a family-scale deployment where the goal is making online
guessing impractical, not surviving restarts.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# Per (scope, key): allow at most MAX_FAILURES failed attempts per WINDOW_SECONDS.
WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 10

_lock = threading.Lock()
_failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _prune(q: deque[float], now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()


def is_blocked(scope: str, key: str) -> tuple[bool, int]:
    """Return (blocked, retry_after_seconds)."""
    now = time.monotonic()
    with _lock:
        q = _failures.get((scope, key))
        if not q:
            return False, 0
        _prune(q, now)
        if len(q) < MAX_FAILURES:
            return False, 0
        retry_after = int(q[0] + WINDOW_SECONDS - now) + 1
        return True, max(retry_after, 1)


def record_failure(scope: str, key: str) -> None:
    now = time.monotonic()
    with _lock:
        q = _failures[(scope, key)]
        _prune(q, now)
        q.append(now)


def reset(scope: str, key: str) -> None:
    with _lock:
        _failures.pop((scope, key), None)


def _clear_all() -> None:
    """For tests only."""
    with _lock:
        _failures.clear()
