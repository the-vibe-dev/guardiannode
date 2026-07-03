"""A background window changing content must trigger a frame even when the
foreground window (and its region hash) is completely unchanged."""
import asyncio
from itertools import chain, repeat

import pytest

from src.config import AgentConfig
from src.main import capture_loop
from src.process_watcher import ActiveProcess
from src.screenshot_capture import Screenshot
from src.window_tracker import WindowInfo


class StopLoop(BaseException):
    pass


def _stop_after(iterations: int):
    state = {"count": 0}

    async def _sleep(_seconds):
        state["count"] += 1
        if state["count"] >= iterations:
            raise StopLoop()

    return _sleep


@pytest.mark.asyncio
async def test_background_change_sends_despite_identical_foreground(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    cfg = AgentConfig(full_screen_capture_enabled=True)

    # Foreground (Notepad) hash never changes; the whole-screen hash flips
    # 32 of 256 bits on the second frame (browser loading behind it).
    shots = [
        Screenshot(width=800, height=600, jpeg_bytes=b"frame1", phash=0, full_phash=0),
        Screenshot(width=800, height=600, jpeg_bytes=b"frame2", phash=0, full_phash=(1 << 32) - 1),
    ]
    state = {"i": 0}

    def fake_capture_full(active_rect=None):
        shot = shots[min(state["i"], len(shots) - 1)]
        state["i"] += 1
        return shot

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="notepad.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="notes", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_full", fake_capture_full)
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_after(2))

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    assert q.qsize() == 2, "first frame + background-change frame must both send"
    first = q.get_nowait()
    second = q.get_nowait()
    assert first["image_bytes"] == b"frame1"
    assert second["image_bytes"] == b"frame2"


@pytest.mark.asyncio
async def test_unchanged_screen_does_not_resend(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    cfg = AgentConfig(full_screen_capture_enabled=True)

    shot = Screenshot(width=800, height=600, jpeg_bytes=b"same", phash=0, full_phash=0)

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="notepad.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="notes", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: shot)
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_after(3))

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    assert q.qsize() == 1, "identical frames after the first must be deduped"


@pytest.mark.asyncio
async def test_unchanged_screen_resends_after_max_capture_interval(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    cfg = AgentConfig(
        full_screen_capture_enabled=True,
        ocr_cadence_seconds=5,
        max_capture_interval_seconds=60,
    )

    shot = Screenshot(width=800, height=600, jpeg_bytes=b"same", phash=0, full_phash=0)
    times = chain([1000.0, 1000.0, 1005.0, 1005.0, 1061.0, 1061.0, 1061.0], repeat(1061.0))

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="notepad.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="notes", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: shot)
    monkeypatch.setattr("src.main.time.time", lambda: next(times))
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_after(3))

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    assert q.qsize() == 2, "first frame + max-interval refresh must send"
