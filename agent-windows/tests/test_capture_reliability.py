import asyncio
from datetime import datetime, timezone

import pytest

from src.config import AgentConfig
from src.main import _apply_capture_config, _capture_is_paused, capture_loop
from src.process_watcher import ActiveProcess
from src.screenshot_capture import Screenshot
from src.window_tracker import WindowInfo


class StopLoop(BaseException):
    pass


def _loop(monkeypatch, shots, *, iterations, current=True):
    state = {"iteration": 0, "monotonic": 0.0, "wall": 10_000.0}
    iterator = iter(shots)
    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    monkeypatch.setattr("src.main.get_active_window", lambda: WindowInfo(
        title="chosen page", rect=(0, 0, 300, 200), hwnd=10, pid=44,
        process=ActiveProcess(44, "chosen.exe", None),
    ))
    monkeypatch.setattr("src.main.window_is_current", lambda _window: current)
    monkeypatch.setattr("src.main.capture_full", lambda **_kwargs: next(iterator))
    monkeypatch.setattr("src.main.capture_active", lambda _rect: next(iterator))
    monkeypatch.setattr("src.main.time.monotonic", lambda: state["monotonic"])
    monkeypatch.setattr("src.main.time.time", lambda: state["wall"])

    async def sleep(_seconds):
        state["iteration"] += 1
        if state["iteration"] >= iterations:
            raise StopLoop()
        state["monotonic"] += 61.0
        state["wall"] -= 3600.0

    monkeypatch.setattr("src.main.asyncio.sleep", sleep)
    return state


def _shot(**kwargs):
    return Screenshot(width=800, height=600, jpeg_bytes=b"synthetic-jpeg", phash=0, full_phash=0, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [0, 65, 256])
async def test_first_frame_is_always_eligible_at_any_valid_threshold(monkeypatch, threshold):
    _loop(monkeypatch, [_shot()], iterations=1)
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, phash_threshold=threshold, full_screen_change_threshold=threshold)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.qsize() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", ["phash_threshold", "full_screen_change_threshold"])
async def test_explicit_zero_threshold_does_not_turn_into_a_default(monkeypatch, setting):
    _loop(monkeypatch, [_shot(), _shot()], iterations=2)
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, max_capture_interval_seconds=3600)
    setattr(cfg, setting, 0)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.qsize() == 2


@pytest.mark.asyncio
async def test_forced_refresh_survives_wall_clock_moving_backwards(monkeypatch):
    _loop(monkeypatch, [_shot(), _shot()], iterations=2)
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, max_capture_interval_seconds=60)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.qsize() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["display_id", "capture_bounds"])
async def test_changed_capture_surface_bypasses_old_scene_dedup(monkeypatch, changed):
    first = {"display_id": "a", "capture_bounds": (0, 0, 800, 600)}
    second = {**first, changed: "b" if changed == "display_id" else (-800, 0, 0, 600)}
    _loop(monkeypatch, [_shot(**first), _shot(**second)], iterations=2)
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, max_capture_interval_seconds=3600)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.qsize() == 2
    for _ in range(2):
        assert "display_id" not in queue.get_nowait()


@pytest.mark.asyncio
async def test_app_capture_is_discarded_when_foreground_changed(monkeypatch):
    _loop(monkeypatch, [_shot()], iterations=1, current=False)
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, apps_and_urls_enabled=True, monitored_apps=["chosen.exe"], full_screen_capture_enabled=False)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["other_display", "changed_foreground"])
async def test_primary_frame_does_not_attach_uncaptured_or_stale_app_context(monkeypatch, reason):
    _loop(monkeypatch, [_shot(active_region_included=reason != "other_display")], iterations=1, current=reason != "changed_foreground")
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True, apps_and_urls_enabled=True)
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    payload = queue.get_nowait()
    assert payload["capture_scope"] == "primary_monitor"
    assert payload["app_name"] is None
    assert payload["window_title"] is None


def test_direct_capture_respects_explicit_server_capture_withdrawal():
    cfg = AgentConfig(monitoring_enabled=True)
    _apply_capture_config(cfg, {"monitoring_enabled": True, "capture_allowed": False})
    assert cfg.monitoring_enabled is False


@pytest.mark.asyncio
async def test_direct_capture_does_not_collect_during_parent_pause(monkeypatch):
    _loop(monkeypatch, [], iterations=1)
    monkeypatch.setattr("src.main.get_active_window", lambda: pytest.fail("parent pause must prevent capture"))
    queue = asyncio.Queue()
    cfg = AgentConfig(monitoring_enabled=True)
    _apply_capture_config(cfg, {
        "monitoring_enabled": True, "paused": True,
        "paused_until": datetime.fromtimestamp(10_100, timezone.utc).isoformat(),
    })
    with pytest.raises(StopLoop):
        await capture_loop(cfg, queue)
    assert queue.empty()


@pytest.mark.parametrize("naive", [False, True])
def test_cached_direct_parent_pause_expires_without_another_backend_poll(monkeypatch, naive):
    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    now = {"time": 10_000}
    monkeypatch.setattr("src.main.time.time", lambda: now["time"])
    until = datetime.fromtimestamp(10_100, timezone.utc)
    if naive:
        until = until.replace(tzinfo=None)
    cfg = AgentConfig()
    _apply_capture_config(cfg, {"monitoring_enabled": True, "paused": True, "paused_until": until.isoformat()})
    assert _capture_is_paused(cfg) is True
    now["time"] = 10_101
    assert _capture_is_paused(cfg) is False
    assert cfg.monitoring_enabled is True


def test_explicit_parent_resume_clears_indefinite_runtime_pause(monkeypatch):
    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    cfg = AgentConfig()
    _apply_capture_config(cfg, {"monitoring_enabled": True, "paused": True, "paused_until": None})
    assert _capture_is_paused(cfg) is True
    _apply_capture_config(cfg, {"monitoring_enabled": True, "paused": False, "paused_until": None})
    assert _capture_is_paused(cfg) is False


def test_malformed_pause_deadline_cannot_permit_capture(monkeypatch):
    monkeypatch.setattr("src.main._is_locally_paused", lambda: False)
    cfg = AgentConfig()
    with pytest.raises(ValueError):
        _apply_capture_config(cfg, {"monitoring_enabled": True, "paused": True, "paused_until": "invalid"})
    assert _capture_is_paused(cfg) is True
