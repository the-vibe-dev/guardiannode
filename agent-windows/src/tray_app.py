"""Child-visible system tray status and parent-dashboard shortcut."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from src.broker_client import BrokerClient
from src.config import AgentConfig, default_config_path
from src.pairing_client import load_credentials

log = logging.getLogger("guardiannode.tray")

# Held for the process lifetime so the OS keeps the mutex alive.
_instance_mutex = None


def already_running() -> bool:
    """Single-instance guard: a second tray launch in the same session exits.

    Session-local (not Global\\) on purpose — each logged-in user gets their
    own tray icon, but duplicate launchers within a session (startup shortcut
    + taskbar pin + installer) collapse to one.
    """
    global _instance_mutex
    if os.name != "nt":
        return False
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GuardianNodeTraySingleton")
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def _backend_url() -> str:
    try:
        backend_url = BrokerClient().status().get("backend_url")
        if backend_url:
            return str(backend_url)
    except Exception:
        pass
    creds = load_credentials() or {}
    if creds.get("backend_url"):
        return creds["backend_url"]
    cfg = AgentConfig.from_path(default_config_path())
    return cfg.backend_url


def _device_id() -> str | None:
    try:
        device_id = BrokerClient().status().get("device_id")
        if device_id:
            return str(device_id)
    except Exception:
        pass
    creds = load_credentials() or {}
    return creds.get("device_id")


def pause_flow() -> None:
    """Pause is parent-authoritative and therefore lives in the signed-in dashboard."""
    _open_dashboard()


def _pause_flag_path() -> str:
    if os.name == "nt":
        return os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "GuardianNode", "paused_until")
    return os.path.expanduser("~/.guardiannode/paused_until")


def _set_local_pause(duration_seconds: int) -> None:
    import time as _t
    path = _pause_flag_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(int(_t.time()) + duration_seconds))


def is_paused() -> bool:
    try:
        return bool(BrokerClient().status().get("paused", False))
    except Exception:
        pass
    import time as _t
    path = _pause_flag_path()
    try:
        with open(path, encoding="utf-8") as f:
            until = int(f.read().strip())
        return _t.time() < until
    except Exception:
        return False


def _try_pystray() -> Callable[[], None] | None:
    """Return a runner if pystray is available, else None."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def _make_image(color: str) -> "Image.Image":
        img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=color)
        return img

    def _load_brand_icon() -> "Image.Image | None":
        """Find the GuardianNode logo: PyInstaller bundle dir, exe dir, or repo."""
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "icon.png")
        candidates.append(Path(sys.executable).resolve().parent / "icon.png")
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / "brand" / "icon.png")
        for p in candidates:
            try:
                if p.is_file():
                    return Image.open(p).convert("RGBA").resize((64, 64))
            except Exception:
                continue
        return None

    def _paused_variant(base: "Image.Image") -> "Image.Image":
        img = base.copy()
        d = ImageDraw.Draw(img)
        d.ellipse((36, 36, 62, 62), fill="#f9a825", outline="white", width=2)
        return img

    def _run() -> None:
        brand = _load_brand_icon()
        green = brand or _make_image("#275e3d")
        yellow = _paused_variant(brand) if brand else _make_image("#f9a825")

        def _menu_pause(icon, item):  # noqa: ANN001
            pause_flow()
            icon.icon = yellow if is_paused() else green

        def _menu_resume(icon, item):  # noqa: ANN001
            _open_dashboard()

        def _menu_exit(icon, item):  # noqa: ANN001
            icon.stop()

        def _status_text(*_args) -> str:
            # Diagnostics: which backend this device reports to + pairing state.
            try:
                status = BrokerClient().status()
                if status.get("paired"):
                    return f"Paired with {status.get('backend_url', '?')}"
            except Exception:
                pass
            creds = load_credentials() or {}
            if creds.get("device_token"):
                return f"Paired with {creds.get('backend_url', '?')}"
            return "Not paired yet"

        def _device_text(*_args) -> str:
            dev = _device_id()
            return f"Device ID: {dev}" if dev else "Device ID: —"

        menu = pystray.Menu(
            pystray.MenuItem(_status_text, None, enabled=False),
            pystray.MenuItem(_device_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ask parent for an exception", lambda *_: _show_child_request_dialog()),
            pystray.MenuItem("View my requests", lambda *_: _show_child_requests()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause monitoring in parent dashboard", _menu_pause),
            pystray.MenuItem("Resume in parent dashboard", _menu_resume),
            pystray.MenuItem("Open dashboard", lambda *_: _open_dashboard()),
            pystray.MenuItem("Exit tray", _menu_exit),
        )
        icon = pystray.Icon("GuardianNode", green if not is_paused() else yellow, "GuardianNode", menu)
        icon.run()

    return _run


def _open_dashboard() -> None:
    import webbrowser
    url = _backend_url().rstrip("/")
    webbrowser.open(url)


def _show_child_request_dialog() -> None:
    """Let a standard user request an exception through broker-owned transport."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Tk()
    window.title("Ask parent — GuardianNode")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=16)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text="What would you like to ask your parent?").grid(row=0, column=0, columnspan=2, sticky="w")
    request_type = tk.StringVar(value="more_time")
    type_box = ttk.Combobox(
        frame, textvariable=request_type, state="readonly",
        values=("more_time", "site_exception", "app_exception", "other"), width=24,
    )
    type_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
    ttk.Label(frame, text="Site or app (optional)").grid(row=2, column=0, sticky="w")
    target = ttk.Entry(frame, width=48)
    target.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))
    ttk.Label(frame, text="Why are you asking? (optional)").grid(row=4, column=0, sticky="w")
    reason = tk.Text(frame, width=48, height=4)
    reason.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 12))

    def submit() -> None:
        payload = {
            "request_type": request_type.get(),
            "target": target.get().strip()[:1024] or None,
            "reason": reason.get("1.0", "end-1c").strip()[:4096] or None,
        }
        try:
            BrokerClient().request("child_request_create", payload)
        except Exception as exc:
            messagebox.showerror("Request not sent", str(exc), parent=window)
            return
        messagebox.showinfo("Request sent", "Your parent can review this request in GuardianNode.", parent=window)
        window.destroy()

    ttk.Button(frame, text="Send request", command=submit).grid(row=6, column=0, sticky="w")
    ttk.Button(frame, text="Cancel", command=window.destroy).grid(row=6, column=1, sticky="e")
    type_box.focus_set()
    window.mainloop()


def _show_child_requests() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        response = BrokerClient().request("child_request_list")
    except Exception as exc:
        messagebox.showerror("Requests unavailable", str(exc))
        return
    items = response.get("items", []) if isinstance(response, dict) else []
    window = tk.Tk()
    window.title("My requests — GuardianNode")
    frame = ttk.Frame(window, padding=16)
    frame.grid(sticky="nsew")
    if not items:
        ttk.Label(frame, text="You have no requests yet.").grid(sticky="w")
    for index, item in enumerate(items[:20]):
        if not isinstance(item, dict):
            continue
        label = f"{item.get('request_type', 'request')}: {item.get('target') or 'general'} — {item.get('status', 'unknown')}"
        ttk.Label(frame, text=label, wraplength=450).grid(row=index, column=0, sticky="w", pady=3)
    ttk.Button(frame, text="Close", command=window.destroy).grid(row=21, column=0, sticky="e", pady=(12, 0))
    window.mainloop()


def _self_test() -> None:
    """Validate dependencies required by the frozen tray without opening UI."""
    import _tkinter  # noqa: F401
    import pystray  # noqa: F401
    import tkinter as tk
    from PIL import Image  # noqa: F401

    interpreter = tk.Tcl()
    if not interpreter.eval("info patchlevel"):
        raise RuntimeError("Tcl interpreter did not report a version")


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode tray app")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.self_test:
        _self_test()
        return

    if already_running():
        log.info("another GuardianNode tray instance is already running in this session; exiting")
        return

    runner = _try_pystray()
    if runner is None:
        log.warning("pystray not installed; running console fallback. Use ctrl+c to quit.")
        # Console fallback: just exit; on Windows the .exe stub will use pystray.
        return
    runner()


if __name__ == "__main__":  # pragma: no cover
    cli()
