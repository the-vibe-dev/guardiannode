"""Small single-process supervisor and readiness registry for background workers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from threading import Lock
from typing import Any

_lock = Lock()
_workers: dict[str, dict[str, Any]] = {}


def _set(name: str, **values: Any) -> None:
    with _lock:
        row = _workers.setdefault(
            name,
            {
                "status": "starting",
                "restarts": 0,
                "last_error": None,
                "started_at": None,
                "updated_at": None,
            },
        )
        row.update(values)
        row["updated_at"] = time.time()


async def supervise(name: str, worker: Callable[[], Awaitable[None]]) -> None:
    """Run a long-lived worker and restart it after an unexpected exit."""
    delay = 1.0
    while True:
        _set(name, status="running", started_at=time.time(), last_error=None)
        try:
            await worker()
            raise RuntimeError("worker exited unexpectedly")
        except asyncio.CancelledError:
            _set(name, status="stopped")
            raise
        except Exception as exc:
            with _lock:
                restarts = int(_workers.get(name, {}).get("restarts", 0)) + 1
            _set(name, status="restarting", restarts=restarts, last_error=str(exc)[:500])
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


def snapshot() -> dict[str, dict[str, Any]]:
    with _lock:
        return {name: dict(row) for name, row in _workers.items()}


def readiness(required: set[str]) -> tuple[bool, dict[str, dict[str, Any]]]:
    rows = snapshot()
    ok = all(rows.get(name, {}).get("status") == "running" for name in required)
    return ok, {name: rows.get(name, {"status": "missing"}) for name in sorted(required)}


def reset_for_tests() -> None:
    with _lock:
        _workers.clear()
