"""Active window title + bounding box."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class WindowInfo:
    title: str
    rect: tuple[int, int, int, int] | None  # left, top, right, bottom


def get_active_window() -> WindowInfo | None:
    if os.name != "nt":
        return WindowInfo(title="dev-window", rect=(0, 0, 1280, 720))
    try:
        import win32gui  # type: ignore
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd) or ""
        rect = win32gui.GetWindowRect(hwnd)
        return WindowInfo(title=title, rect=rect)
    except Exception:
        return None
