"""Foreground and DPI behavior through synthetic Windows API contracts."""
from contextlib import nullcontext
import sys
from types import SimpleNamespace

import psutil
import pytest
from PIL import Image

from src import display_coordinates, process_watcher, screenshot_capture, window_tracker
from src.process_watcher import ActiveProcess


def _windows(monkeypatch, *, foreground=None):
    state = {"hwnd": 10, "pid": 44, "rect": (100, 200, 900, 800), "title": "chosen", "visible": True, "iconic": False}
    gui = SimpleNamespace(
        GetForegroundWindow=foreground or (lambda: state["hwnd"]),
        GetWindowText=lambda hwnd: state["title"],
        GetWindowRect=lambda hwnd: state["rect"],
        IsWindowVisible=lambda hwnd: state["visible"],
        IsIconic=lambda hwnd: state["iconic"],
    )
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32process", SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, state["pid"])))
    monkeypatch.setattr(window_tracker, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(window_tracker, "physical_pixel_coordinates", nullcontext)
    monkeypatch.setattr(window_tracker, "get_process", lambda pid: ActiveProcess(pid, "chosen.exe", None))
    return state


def test_window_and_process_use_the_same_sampled_hwnd(monkeypatch):
    _windows(monkeypatch)
    window = window_tracker.get_active_window()
    assert window.hwnd == 10
    assert window.pid == window.process.pid == 44
    assert window.title == "chosen"
    assert window.rect == (100, 200, 900, 800)
    assert window_tracker.window_is_current(window)


def test_focus_change_while_sampling_is_rejected(monkeypatch):
    hwnds = iter([10, 20])
    _windows(monkeypatch, foreground=lambda: next(hwnds))
    assert window_tracker.get_active_window() is None


@pytest.mark.parametrize("key,value", [
    ("hwnd", 20), ("pid", 55), ("rect", (200, 200, 1000, 800)),
    ("title", "new page"), ("visible", False), ("iconic", True),
])
def test_changed_window_is_not_reused_after_capture(monkeypatch, key, value):
    state = _windows(monkeypatch)
    window = window_tracker.get_active_window()
    state[key] = value
    assert window_tracker.window_is_current(window) is False


@pytest.mark.parametrize("key", ["visible", "iconic"])
def test_hidden_or_minimized_foreground_is_not_a_capture_target(monkeypatch, key):
    state = _windows(monkeypatch)
    state[key] = key == "iconic"
    assert window_tracker.get_active_window() is None


def test_process_name_remains_usable_when_executable_path_is_protected(monkeypatch):
    def protected_exe():
        raise psutil.AccessDenied(pid=44)

    monkeypatch.setattr(process_watcher.psutil, "Process", lambda pid: SimpleNamespace(name=lambda: "chosen.exe", exe=protected_exe))
    assert process_watcher.get_process(44) == ActiveProcess(44, "chosen.exe", None)


@pytest.mark.parametrize("v2_supported", [True, False])
def test_dpi_context_is_restored_even_when_capture_raises(monkeypatch, v2_supported):
    calls = []

    class SetContext:
        def __call__(self, value):
            value = value.value if hasattr(value, "value") else value
            calls.append(value)
            if len(calls) == 1 and not v2_supported:
                return None
            return 123

    monkeypatch.setattr(display_coordinates, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(display_coordinates.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(SetThreadDpiAwarenessContext=SetContext()), raising=False)
    with pytest.raises(RuntimeError, match="capture failed"):
        with display_coordinates.physical_pixel_coordinates():
            raise RuntimeError("capture failed")
    assert calls[-1] == 123
    assert len(calls) == (2 if v2_supported else 3)


def test_unavailable_physical_coordinates_do_not_proceed_with_virtualized_bounds(monkeypatch):
    class SetContext:
        def __call__(self, _value):
            return None

    monkeypatch.setattr(display_coordinates, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(display_coordinates.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(SetThreadDpiAwarenessContext=SetContext()), raising=False)
    with pytest.raises(OSError, match="physical capture coordinates"):
        with display_coordinates.physical_pixel_coordinates():
            pytest.fail("unsafe coordinate reads must not run")


def test_first_window_bounds_and_capture_share_physical_pixels_before_mss_initialization(monkeypatch):
    _windows(monkeypatch)
    state = {"dpi": 1}
    physical = (100, 200, 900, 800)

    class SetContext:
        def __call__(self, value):
            previous = state["dpi"]
            state["dpi"] = value.value if hasattr(value, "value") else value
            return previous

    class Screen:
        def __enter__(self):
            assert state["dpi"] != 1
            self.monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
            return self

        def __exit__(self, *_args):
            return False

        def grab(self, rect):
            assert state["dpi"] != 1
            assert rect == {"left": 100, "top": 200, "width": 800, "height": 600}
            image = Image.new("RGB", (800, 600))
            return SimpleNamespace(size=image.size, rgb=image.tobytes())

    monkeypatch.setattr(display_coordinates, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(display_coordinates.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(SetThreadDpiAwarenessContext=SetContext()), raising=False)
    monkeypatch.setattr(window_tracker, "physical_pixel_coordinates", display_coordinates.physical_pixel_coordinates)
    monkeypatch.setattr(sys.modules["win32gui"], "GetWindowRect", lambda _hwnd: physical if state["dpi"] != 1 else (50, 100, 450, 400))
    monkeypatch.setattr(screenshot_capture.mss, "mss", Screen)
    window = window_tracker.get_active_window()
    assert window.rect == physical
    assert state["dpi"] == 1
    shot = screenshot_capture.capture_active(window.rect)
    assert shot.capture_bounds == physical
    assert state["dpi"] == 1
