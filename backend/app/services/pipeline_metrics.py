"""Live pipeline metrics — what's currently being classified, plus recent throughput.

This is a module-level in-memory store (resets on backend restart). Suitable
for a single-process Uvicorn deployment. If we move to multi-worker we'd back
this with Redis or similar; for the family-LAN use case in-process is fine.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class InFlightItem:
    event_id: str
    started_at: float
    tier: str
    app_name: str | None = None
    window_title: str | None = None
    device_id: str | None = None
    stage: str = "queued"  # queued | vision_llm | text_llm | merging | storing

    def elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tier": self.tier,
            "app_name": self.app_name,
            "window_title": (self.window_title or "")[:120],
            "device_id": self.device_id,
            "stage": self.stage,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms(),
        }


@dataclass
class CompletedItem:
    event_id: str
    finished_at: float
    latency_ms: int
    severity: str
    tier: str


_lock = Lock()
_in_flight: dict[str, InFlightItem] = {}
# Agent-side upload backlog, reported via device heartbeats:
# device_id -> (hostname, queued_frames, reported_at)
_agent_queues: dict[str, tuple[str, int, float]] = {}
# rolling window of completed items; we keep last 200 for stats
_recent: deque[CompletedItem] = deque(maxlen=200)


def start(
    *,
    event_id: str,
    tier: str,
    app_name: str | None = None,
    window_title: str | None = None,
    device_id: str | None = None,
) -> None:
    with _lock:
        _in_flight[event_id] = InFlightItem(
            event_id=event_id,
            started_at=time.time(),
            tier=tier,
            app_name=app_name,
            window_title=window_title,
            device_id=device_id,
        )


def set_stage(event_id: str, stage: str) -> None:
    with _lock:
        item = _in_flight.get(event_id)
        if item is not None:
            item.stage = stage


def finish(event_id: str, *, severity: str) -> None:
    with _lock:
        item = _in_flight.pop(event_id, None)
        if item is None:
            return
        now = time.time()
        _recent.append(
            CompletedItem(
                event_id=event_id,
                finished_at=now,
                latency_ms=int((now - item.started_at) * 1000),
                severity=severity,
                tier=item.tier,
            )
        )


def snapshot(window_seconds: int = 60) -> dict[str, Any]:
    """Snapshot of current state. Safe to call from request handlers."""
    now = time.time()
    cutoff = now - window_seconds
    with _lock:
        items = [item.to_dict() for item in _in_flight.values()]
        recent_completed = [c for c in _recent if c.finished_at >= cutoff]
    items.sort(key=lambda d: d["started_at"])

    latencies = sorted(c.latency_ms for c in recent_completed)
    n = len(latencies)
    avg = sum(latencies) / n if n else 0
    p50 = latencies[n // 2] if n else 0
    p95 = latencies[int(n * 0.95)] if n else 0
    severity_counts: dict[str, int] = {}
    for c in recent_completed:
        severity_counts[c.severity] = severity_counts.get(c.severity, 0) + 1

    return {
        "in_flight_count": len(items),
        "in_flight": items,
        "window_seconds": window_seconds,
        "throughput": {
            "frames_in_window": n,
            "avg_latency_ms": int(avg),
            "p50_latency_ms": int(p50),
            "p95_latency_ms": int(p95),
            "severity_counts": severity_counts,
        },
    }


def record_agent_queue(device_id: str, hostname: str, queued_frames: int) -> None:
    """Called from the device heartbeat: how many frames the agent is holding."""
    with _lock:
        _agent_queues[device_id] = (hostname, int(queued_frames), time.time())


def agent_queues(max_age_seconds: int = 120) -> list[dict[str, Any]]:
    """Recent agent backlog reports (stale entries are dropped from the view)."""
    now = time.time()
    with _lock:
        return [
            {
                "device_id": device_id,
                "hostname": hostname,
                "queued_frames": queued,
                "age_seconds": int(now - ts),
            }
            for device_id, (hostname, queued, ts) in _agent_queues.items()
            if now - ts <= max_age_seconds
        ]


def reset_for_tests() -> None:
    with _lock:
        _in_flight.clear()
        _recent.clear()
        _agent_queues.clear()
