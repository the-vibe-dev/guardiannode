"""Screen capture via mss + perceptual-hash based change detection."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

try:
    import mss  # type: ignore
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False


log = logging.getLogger("guardiannode.agent.capture")
_warned_no_mss = False
_warned_active_error = False
_warned_full_error = False


@dataclass
class Screenshot:
    width: int
    height: int
    jpeg_bytes: bytes
    phash: int  # high-resolution dHash, region-scoped when available
    full_phash: int | None = None  # 256-bit dHash of the whole encoded frame


def _encode_jpeg(img, quality: int = 80, max_dim: int = 1600) -> bytes:
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _dhash(img, hash_size: int = 8) -> int:
    """Difference hash. With the default 8x8 grid, returns a 64-bit int.

    Robust to compression and small content shifts; sensitive to genuine scene
    changes. Distance is Hamming distance between two hashes.
    """
    from PIL import Image
    g = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = list(g.getdata())
    h = 0
    row_width = hash_size + 1
    for y in range(hash_size):
        row = y * row_width
        for x in range(hash_size):
            h = (h << 1) | (1 if px[row + x] < px[row + x + 1] else 0)
    return h


def _clamp_rect(
    rect: tuple[int, int, int, int],
    mon_left: int, mon_top: int, mon_w: int, mon_h: int,
) -> tuple[int, int, int, int] | None:
    """Clip an absolute-screen rect to monitor bounds, return (x, y, w, h)
    relative to the monitor origin. Returns None if the rect is degenerate.
    """
    left, top, right, bottom = rect
    # Translate to monitor-local
    x0 = max(0, left - mon_left)
    y0 = max(0, top - mon_top)
    x1 = min(mon_w, right - mon_left)
    y1 = min(mon_h, bottom - mon_top)
    w, h = x1 - x0, y1 - y0
    if w < 32 or h < 32:
        return None
    return x0, y0, w, h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def capture_active(rect: tuple[int, int, int, int] | None) -> Screenshot | None:
    global _warned_no_mss, _warned_active_error
    if not _HAS_MSS or not rect:
        if not _HAS_MSS and not _warned_no_mss:
            log.warning("screen capture unavailable: mss is not installed")
            _warned_no_mss = True
        return None
    left, top, right, bottom = rect
    w, h = max(1, right - left), max(1, bottom - top)
    region = {"left": left, "top": top, "width": w, "height": h}
    try:
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            phash = _dhash(img, hash_size=16)
            jpeg = _encode_jpeg(img, quality=80, max_dim=1600)
            return Screenshot(width=w, height=h, jpeg_bytes=jpeg, phash=phash, full_phash=phash)
    except Exception as e:
        if not _warned_active_error:
            log.warning("active-window capture failed: %s", e)
            _warned_active_error = True
        return None


def capture_full(active_rect: tuple[int, int, int, int] | None = None) -> Screenshot | None:
    """Whole-primary-monitor capture.

    Catches content in background apps / wallpapers / picture viewers — anything
    visually present on the user's desktop, not just the focused window.

    If `active_rect` (absolute screen coordinates of the foreground window) is
    given, the dedup phash is computed on that subregion of the captured frame
    instead of the whole monitor. This makes the hash sensitive to small text
    changes inside the active window (e.g. lines added/removed in Notepad) that
    would otherwise be invisible at full-screen 8x8 dHash resolution. The
    encoded JPEG remains the full screen.
    """
    global _warned_no_mss, _warned_full_error
    if not _HAS_MSS:
        if not _warned_no_mss:
            log.warning("screen capture unavailable: mss is not installed")
            _warned_no_mss = True
        return None
    try:
        from PIL import Image
        with mss.mss() as sct:
            mons = sct.monitors
            # mons[0] is the union of all monitors; mons[1] is the primary.
            # We prefer the primary to keep frame size manageable on multi-monitor setups.
            mon = mons[1] if len(mons) > 1 else mons[0]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.rgb)

            phash_img = img
            if active_rect is not None:
                clipped = _clamp_rect(
                    active_rect,
                    mon.get("left", 0), mon.get("top", 0),
                    mon["width"], mon["height"],
                )
                if clipped is not None:
                    x0, y0, w, h = clipped
                    phash_img = img.crop((x0, y0, x0 + w, y0 + h))

            full_phash = _dhash(img, hash_size=16)
            # A 64-bit hash is too coarse for a few newly typed terminal
            # characters. Match the full-frame hash resolution so small text
            # changes survive downsampling.
            phash = _dhash(phash_img, hash_size=16)
            jpeg = _encode_jpeg(img, quality=80, max_dim=1600)
            return Screenshot(
                width=mon["width"],
                height=mon["height"],
                jpeg_bytes=jpeg,
                phash=phash,
                full_phash=full_phash,
            )
    except Exception as e:
        if not _warned_full_error:
            log.warning("full-screen capture failed: %s", e)
            _warned_full_error = True
        return None
