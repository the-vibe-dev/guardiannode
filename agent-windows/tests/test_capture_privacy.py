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
