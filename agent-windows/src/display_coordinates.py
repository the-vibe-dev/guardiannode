"""Keep Windows window bounds and capture pixels in the same coordinate space."""
from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager


@contextmanager
def physical_pixel_coordinates():
    """Temporarily use per-monitor DPI awareness on this capture thread.

    GetWindowRect is DPI-virtualized otherwise, including before MSS first
    initializes. Changing the thread context also works when a process DPI
    mode was already chosen by an executable manifest or another library.
    """
    if os.name != "nt":
        yield
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    set_context = user32.SetThreadDpiAwarenessContext
    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_void_p
    # Per-monitor v2 (Windows 10 1703+), then v1 (Windows 10 1607).
    previous = set_context(ctypes.c_void_p(-4)) or set_context(ctypes.c_void_p(-3))
    if not previous:
        raise OSError("could not establish physical capture coordinates")
    try:
        yield
    finally:
        set_context(previous)
