"""Active window title + bounding box."""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.display_coordinates import physical_pixel_coordinates
from src.process_watcher import ActiveProcess, get_active_process, get_process


@dataclass
class WindowInfo:
    title: str
    rect: tuple[int, int, int, int] | None  # left, top, right, bottom
    hwnd: int | None = None
    pid: int | None = None
    process: ActiveProcess | None = None


def get_active_window() -> WindowInfo | None:
    if os.name != "nt":
        return WindowInfo(title="dev-window", rect=(0, 0, 1280, 720), process=get_active_process())
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore
        with physical_pixel_coordinates():
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return None
            process = get_process(pid)
            title = win32gui.GetWindowText(hwnd) or ""
            rect = win32gui.GetWindowRect(hwnd)
            if (
                win32gui.GetForegroundWindow() != hwnd
                or win32process.GetWindowThreadProcessId(hwnd)[1] != pid
            ):
                return None
            return WindowInfo(title=title, rect=rect, hwnd=hwnd, pid=pid, process=process)
    except Exception:
        return None


def window_is_current(window: WindowInfo) -> bool:
    """Reject stale bounds/context when focus or the window moves mid-capture."""
    if os.name != "nt":
        return True
    if window.hwnd is None or window.pid is None:
        return False
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore
        with physical_pixel_coordinates():
            return (
                win32gui.GetForegroundWindow() == window.hwnd
                and win32process.GetWindowThreadProcessId(window.hwnd)[1] == window.pid
                and win32gui.IsWindowVisible(window.hwnd)
                and not win32gui.IsIconic(window.hwnd)
                and win32gui.GetWindowRect(window.hwnd) == window.rect
                and (win32gui.GetWindowText(window.hwnd) or "") == window.title
            )
    except Exception:
        return False
