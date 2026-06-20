"""Detect active foreground process across Windows and (for dev) Linux."""
from __future__ import annotations

import os
from dataclasses import dataclass

import psutil


@dataclass
class ActiveProcess:
    pid: int
    name: str
    exe: str | None


def _windows_foreground() -> ActiveProcess | None:
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore
    except ImportError:
        return None
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return None
        p = psutil.Process(pid)
        return ActiveProcess(pid=pid, name=p.name(), exe=p.exe() if p else None)
    except Exception:
        return None


def _linux_active() -> ActiveProcess | None:
    """Dev fallback: just return current Python proc so the loop works on Linux."""
    me = psutil.Process(os.getpid())
    return ActiveProcess(pid=me.pid, name=me.name(), exe=me.exe())


def get_active_process() -> ActiveProcess | None:
    if os.name == "nt":
        return _windows_foreground()
    return _linux_active()


def is_monitored(active: ActiveProcess | None, monitored_apps: list[str]) -> bool:
    if active is None or not active.name:
        return False
    name = active.name.lower()
    return any(name == app.lower() for app in monitored_apps)
