import asyncio

import pytest

from src.config import AgentConfig
from src.main import capture_loop
from src.process_watcher import ActiveProcess
from src.screenshot_capture import Screenshot
from src.window_tracker import WindowInfo


class StopLoop(BaseException):
    pass


async def _stop_sleep(_seconds):
    raise StopLoop()


def _stop_after(iterations: int):
    state = {"count": 0}

    async def _sleep(_seconds):
        state["count"] += 1
        if state["count"] >= iterations:
            raise StopLoop()

    return _sleep


@pytest.mark.asyncio
async def test_unmonitored_app_does_not_enqueue_screenshot(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=2)
    cfg = AgentConfig(monitored_apps=["Roblox.exe"], full_screen_capture_enabled=False)

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="notepad.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="notes", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_active", lambda _rect: pytest.fail("capture_active called"))
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: pytest.fail("capture_full called"))
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_sleep)

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)
    assert q.empty()


@pytest.mark.asyncio
async def test_monitored_app_enqueues_window_scoped_metadata(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=2)
    cfg = AgentConfig(
        profile_id="child-1",
        age_group="under_10",
        policy_id="policy-1",
        policy_version="2",
        monitored_apps=["Roblox.exe"],
        full_screen_capture_enabled=False,
    )

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="Roblox.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="Roblox", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr(
        "src.main.capture_active",
        lambda _rect: Screenshot(width=300, height=200, jpeg_bytes=b"jpg", phash=123),
    )
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: pytest.fail("capture_full called"))
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_sleep)

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    payload = q.get_nowait()
    assert payload["app_name"] == "Roblox.exe"
    assert payload["profile_id"] == "child-1"
    assert payload["age_group"] == "under_10"
    assert payload["policy_id"] == "policy-1"
    assert payload["policy_version"] == "2"
    assert payload["capture_scope"] == "monitored_app"
    assert payload["in_monitored"] is True


@pytest.mark.asyncio
async def test_full_screen_mode_keeps_monitored_app_region_change(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    cfg = AgentConfig(
        monitored_apps=["notepad.exe"],
        full_screen_capture_enabled=True,
        phash_threshold=2,
    )

    shots = iter([
        Screenshot(width=800, height=600, jpeg_bytes=b"jpg-1", phash=0b00000000, full_phash=0b10101010),
        # Active-region hash changes, but full-screen hash is identical.
        Screenshot(width=800, height=600, jpeg_bytes=b"jpg-2", phash=0b11110000, full_phash=0b10101010),
    ])

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="notepad.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="notes", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: next(shots))
    monkeypatch.setattr("src.main.capture_active", lambda _rect: pytest.fail("capture_active called"))
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_after(2))

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_full_screen_mode_treats_every_foreground_app_as_monitored(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    cfg = AgentConfig(
        monitored_apps=["notepad.exe"],
        full_screen_capture_enabled=True,
        phash_threshold=2,
    )

    shots = iter([
        Screenshot(width=800, height=600, jpeg_bytes=b"jpg-1", phash=0, full_phash=0),
        Screenshot(width=800, height=600, jpeg_bytes=b"jpg-2", phash=0b11110000, full_phash=0),
    ])

    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr(
        "src.main.get_active_process",
        lambda: ActiveProcess(pid=1, name="putty.exe", exe=None),
    )
    monkeypatch.setattr(
        "src.main.get_active_window",
        lambda: WindowInfo(title="terminal", rect=(0, 0, 300, 200)),
    )
    monkeypatch.setattr("src.main.capture_full", lambda active_rect=None: next(shots))
    monkeypatch.setattr("src.main.asyncio.sleep", _stop_after(2))

    with pytest.raises(StopLoop):
        await capture_loop(cfg, q)

    assert q.qsize() == 2
