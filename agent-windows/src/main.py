"""Agent main loop.

- Detects active foreground app
- If monitored, captures active-window screenshot (JPEG)
- Perceptual-hash dedups identical frames
- POSTs JPEG bytes to backend's /api/events/screenshot
- Backend does vision-LLM OCR + classification (or Tesseract fallback)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from src import __version__
from src.backend_client import BackendClient
from src.config import AgentConfig, default_config_path
from src.pairing_client import bootstrap_pairing, load_credentials, pair_with_server, save_credentials
from src.process_watcher import get_active_process, is_monitored
from src.screenshot_capture import capture_active, capture_full, hamming
from src.window_tracker import get_active_window

log = logging.getLogger("guardiannode.agent")


def _is_locally_paused() -> bool:
    if os.name == "nt":
        path = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "GuardianNode", "paused_until")
    else:
        path = os.path.expanduser("~/.guardiannode/paused_until")
    try:
        with open(path, encoding="utf-8") as f:
            return time.time() < int(f.read().strip())
    except Exception:
        return False


async def capture_loop(cfg: AgentConfig, screenshot_queue: asyncio.Queue) -> None:
    """Screenshot loop. Captures active monitored window, perceptual-hash dedups,
    queues JPEG bytes for the sender to ship to the backend.
    """
    # Perceptual-hash threshold. Hamming distance over 64-bit dHash computed
    # on the foreground window region (see capture_full(active_rect=…)).
    #  - 0..1  : near-identical (cursor blink, idle screen): skip
    #  - 2..3  : a single-character / single-line edit in a text app: send
    #  - 4+    : clear scene change: send
    PHASH_THRESHOLD = int(getattr(cfg, "phash_threshold", 0) or 2)
    FULL_DUP_THRESHOLD = int(getattr(cfg, "full_screen_duplicate_threshold", 0) or 3)
    # Whole-screen change is an independent trigger: a background window
    # loading new content (e.g. a browser behind Notepad) must send a frame
    # even when the foreground window hash is unchanged. full_phash is a
    # 256-bit dHash, so small noise (clock tick) stays below this.
    FULL_CHANGE_THRESHOLD = int(getattr(cfg, "full_screen_change_threshold", 0) or 10)

    last_phash: int | None = None
    last_full_phash: int | None = None
    sent_count = 0
    skipped_count = 0
    last_log_summary = time.time()

    while True:
        try:
            if _is_locally_paused():
                log.debug("monitoring paused locally; skipping capture")
                await asyncio.sleep(cfg.ocr_cadence_seconds)
                continue

            active = get_active_process()
            win = get_active_window()
            app_name = active.name if active else None
            win_title = win.title if win else None
            active_rect = win.rect if win else None
            in_monitored = is_monitored(active, cfg.monitored_apps)

            if not in_monitored and not cfg.full_screen_capture_enabled:
                log.debug("active app is not monitored; skipping capture: %s", app_name)
                await asyncio.sleep(cfg.ocr_cadence_seconds)
                continue

            capture_scope = "full_screen_opt_in" if cfg.full_screen_capture_enabled else "monitored_app"
            shot = (
                capture_full(active_rect=active_rect)
                if cfg.full_screen_capture_enabled
                else capture_active(active_rect)
            )
            if not shot:
                await asyncio.sleep(cfg.ocr_cadence_seconds)
                continue

            # Perceptual diff: only ship if the scene actually changed.
            # First frame always sends (dist=64 sentinel forces it).
            dist = 64 if last_phash is None else hamming(last_phash, shot.phash)
            full_dist = 64
            full_known = shot.full_phash is not None and last_full_phash is not None
            if full_known:
                full_dist = hamming(last_full_phash, shot.full_phash)
            send = dist >= PHASH_THRESHOLD

            # Foreground-hash triggers that the whole screen says are noise → skip.
            if send and cfg.full_screen_capture_enabled and full_known and full_dist < FULL_DUP_THRESHOLD:
                send = False

            # Whole-screen trigger: catches background windows changing content
            # while the foreground window (and its hash) stays identical.
            if not send and cfg.full_screen_capture_enabled and full_known and full_dist >= FULL_CHANGE_THRESHOLD:
                send = True

            if cfg.dry_run:
                log.info(
                    "dry-run: app=%s monitored=%s phash_dist=%d full_phash_dist=%d send=%s bytes=%d",
                    app_name, in_monitored, dist, full_dist, send, len(shot.jpeg_bytes),
                )

            if send:
                last_phash = shot.phash
                last_full_phash = shot.full_phash
                sent_count += 1
                payload = {
                    "image_bytes": shot.jpeg_bytes,
                    "app_name": app_name,
                    "window_title": win_title,
                    "profile_id": cfg.profile_id,
                    "age_group": cfg.age_group,
                    "capture_scope": capture_scope,
                    "policy_id": cfg.policy_id,
                    "policy_version": cfg.policy_version,
                    "collector_version": __version__,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "phash_dist": dist,
                    "full_phash_dist": full_dist,
                    "in_monitored": in_monitored,
                }
                if not cfg.dry_run:
                    # If the backend is slower than the capture rate, keep the
                    # FRESHEST frames: drop the oldest queued frame to make room
                    # rather than dropping this new one. Otherwise the parent
                    # would see minutes-stale classifications.
                    dropped = 0
                    while True:
                        try:
                            screenshot_queue.put_nowait(payload)
                            break
                        except asyncio.QueueFull:
                            try:
                                screenshot_queue.get_nowait()
                                screenshot_queue.task_done()
                                dropped += 1
                            except asyncio.QueueEmpty:
                                break
                    log.info(
                        "queued frame: app=%s monitored=%s phash_dist=%d full_phash_dist=%d bytes=%d%s",
                        app_name, in_monitored, dist, full_dist, len(shot.jpeg_bytes),
                        f" (dropped {dropped} stale)" if dropped else "",
                    )
            else:
                skipped_count += 1

            # Roll up "skipped N identical frames" so the log isn't silent when
            # nothing changes. Liveness is signaled separately by heartbeat_loop().
            now = time.time()
            if now - last_log_summary > 300:  # every 5 minutes
                log.info(
                    "capture summary: sent=%d skipped=%d (skip rate=%.0f%%)",
                    sent_count, skipped_count,
                    100 * skipped_count / max(1, sent_count + skipped_count),
                )
                last_log_summary = now
        except Exception as e:
            log.warning("capture loop error: %s", e)
        await asyncio.sleep(cfg.ocr_cadence_seconds)


async def screenshot_sender_loop(client: BackendClient, screenshot_queue: asyncio.Queue) -> None:
    """Drains the screenshot queue, posts each frame to /api/events/screenshot.
    Retries on transient failure with bounded backoff.
    """
    backoff = 1.0
    while True:
        try:
            payload = await screenshot_queue.get()
            try:
                result = await client.send_screenshot(
                    image_bytes=payload["image_bytes"],
                    app_name=payload.get("app_name"),
                    window_title=payload.get("window_title"),
                    profile_id=payload.get("profile_id"),
                    age_group=payload.get("age_group", "10_13"),
                    capture_scope=payload.get("capture_scope", "monitored_app"),
                    policy_id=payload.get("policy_id"),
                    policy_version=payload.get("policy_version"),
                    collector_version=payload.get("collector_version"),
                    timestamp=payload.get("timestamp"),
                )
                # The backend stores the frame and classifies it in the
                # background, so this returns immediately with a queued ack.
                log.info(
                    "ship app=%s bytes=%d → %s",
                    payload.get("app_name"),
                    len(payload["image_bytes"]),
                    result.get("status", "ok"),
                )
                backoff = 1.0
            except Exception as e:
                log.warning("screenshot send failed (%s); requeueing", e)
                # Keep the freshest frames if a transient failure backs us up.
                while True:
                    try:
                        screenshot_queue.put_nowait(payload)
                        break
                    except asyncio.QueueFull:
                        try:
                            screenshot_queue.get_nowait()
                            screenshot_queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
        except Exception as e:
            log.warning("sender loop error: %s", e)
            await asyncio.sleep(5)


async def heartbeat_loop(client: BackendClient, screenshot_queue: asyncio.Queue) -> None:
    while True:
        try:
            ok = await client.heartbeat(queued_frames=screenshot_queue.qsize())
            if not ok:
                log.debug("heartbeat: backend unreachable")
        except Exception as e:
            log.debug("heartbeat error: %s", e)
        await asyncio.sleep(30)


async def main_async(cfg: AgentConfig) -> None:
    # Complete pairing left pending by the installer (or a previous failed run).
    try:
        await asyncio.to_thread(bootstrap_pairing, socket.gethostname(), __version__)
    except Exception as e:
        log.warning("pairing bootstrap failed: %s", e)
    creds = load_credentials() or {}
    backend_url = creds.get("backend_url", cfg.backend_url)
    token = creds.get("device_token", cfg.device_token)
    if not token and not cfg.dry_run:
        log.warning("no device token — agent will only queue events locally until paired")

    # In-memory screenshot queue (size-capped for backpressure)
    screenshot_queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    client = BackendClient(backend_url, token)

    log.info(
        "agent started: backend=%s cadence=%ds monitored_apps=%d",
        backend_url, cfg.ocr_cadence_seconds, len(cfg.monitored_apps),
    )

    await asyncio.gather(
        capture_loop(cfg, screenshot_queue),
        screenshot_sender_loop(client, screenshot_queue),
        heartbeat_loop(client, screenshot_queue),
    )


# Held for the process lifetime so the OS keeps the mutex alive.
_instance_mutex = None


def already_running() -> bool:
    """Per-session single-instance guard. One agent per logged-in session;
    duplicate launchers (startup shortcut + scheduled task + installer) collapse."""
    global _instance_mutex
    if os.name != "nt":
        return False
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GuardianNodeAgentSingleton")
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def _log_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "GuardianNode" / "logs"
    else:
        base = Path.home() / ".guardiannode" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "agent.log"


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode Windows agent")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--dry-run", action="store_true", help="don't send events, just log")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--pair", action="store_true", help="pair with a backend and exit")
    parser.add_argument("--server", help="backend URL for --pair (e.g. http://192.168.1.42:8787)")
    parser.add_argument("--code", help="6-digit pairing code for --pair")
    args = parser.parse_args()

    # File handler so a --windowed (no-console) PyInstaller bundle still leaves a trail.
    handlers: list[logging.Handler] = []
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(_log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handlers.append(fh)
    except Exception:
        pass
    # Console handler is harmless if there's no console (PyInstaller --windowed will drop it).
    try:
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handlers.append(sh)
    except Exception:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )

    cfg = AgentConfig.from_path(args.config)

    if args.pair:
        if not args.code:
            parser.error("--pair requires --code (and usually --server)")
        server = args.server or cfg.backend_url
        try:
            device_id, token = pair_with_server(server, args.code, socket.gethostname(), agent_version=__version__)
        except Exception as e:
            log.error("pairing failed: %s", e)
            raise SystemExit(1)
        path = save_credentials(device_id, token, server)
        log.info("paired with %s as device %s (credentials: %s)", server, device_id, path)
        print(f"Paired successfully. Device ID: {device_id}")
        return

    if args.dry_run:
        cfg.dry_run = True
    cfg.dry_run = cfg.dry_run or os.environ.get("GUARDIANNODE_DRY_RUN") == "1"

    if already_running():
        log.info("another GuardianNode agent is already running in this session; exiting")
        return

    log.info("GuardianNode agent %s starting (hostname=%s)", __version__, socket.gethostname())
    try:
        asyncio.run(main_async(cfg))
    except KeyboardInterrupt:
        log.info("agent stopped by user")


if __name__ == "__main__":  # pragma: no cover
    cli()
