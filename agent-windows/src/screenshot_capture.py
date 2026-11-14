"""Screen capture via mss + perceptual-hash based change detection."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from src.broker_protocol import MAX_SCREENSHOT_BYTES
from src.display_coordinates import physical_pixel_coordinates

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
    capture_bounds: tuple[int, int, int, int] | None = None  # physical desktop coordinates
    display_id: str | None = None  # local dedup identity; never sent to the backend
    active_region_included: bool | None = None


def _encode_jpeg(img, quality: int = 80, max_dim: int = 1600) -> bytes:
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
    # High-entropy frames (games, wallpapers, square HiDPI displays) can
    # exceed the broker's existing payload bound even after resizing. Keep
    # the highest fitting quality instead of repeatedly losing those frames.
    while True:
        for candidate in list(range(quality, 39, -10)) or [quality]:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=candidate, optimize=True)
            encoded = buf.getvalue()
            if len(encoded) <= MAX_SCREENSHOT_BYTES:
                return encoded
        if img.size == (1, 1):
            raise ValueError("screenshot cannot fit the broker payload size")
        img.thumbnail((max(1, img.width * 3 // 4), max(1, img.height * 3 // 4)))


def _dhash(img, hash_size: int = 8) -> int:
    """Difference hash. With the default 8x8 grid, returns a 64-bit int.

    Robust to compression and small content shifts; sensitive to genuine scene
    changes. Distance is Hamming distance between two hashes.
    """
    from PIL import Image
    g = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = g.tobytes()
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
    *, min_size: int = 32,
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
    if w < min_size or h < min_size:
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
    try:
        from PIL import Image
        with physical_pixel_coordinates(), mss.mss() as sct:
            if not sct.monitors:
                return None
            desktop = sct.monitors[0]
            clipped = _clamp_rect(
                rect, desktop["left"], desktop["top"],
                desktop["width"], desktop["height"], min_size=1,
            )
            if clipped is None:
                return None
            x0, y0, w, h = clipped
            left, top = desktop["left"] + x0, desktop["top"] + y0
            region = {"left": left, "top": top, "width": w, "height": h}
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            phash = _dhash(img, hash_size=16)
            jpeg = _encode_jpeg(img, quality=80, max_dim=1600)
            return Screenshot(
                width=img.width, height=img.height, jpeg_bytes=jpeg,
                phash=phash, full_phash=phash,
                capture_bounds=(left, top, left + w, top + h),
                active_region_included=True,
            )
    except Exception as e:
        if not _warned_active_error:
            log.warning("active-window capture failed: %s", e)
            _warned_active_error = True
        return None


def capture_full(active_rect: tuple[int, int, int, int] | None = None) -> Screenshot | None:
    """Whole-primary-monitor capture.

    Catches content in background apps / wallpapers / picture viewers on the
    primary display, not just the focused window. Other monitors are outside
    this capture region and must not be described as covered.

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
        with physical_pixel_coordinates(), mss.mss() as sct:
            mons = sct.monitors
            # Enumeration order is not a primary-display guarantee. Newer MSS
            # versions expose the Windows primary flag. Older backends retain
            # the first-physical-display fallback, never the all-display union.
            physical = mons[1:]
            if not physical:
                return None
            mon = next((item for item in physical if item.get("is_primary") is True), physical[0])
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.rgb)

            phash_img = img
            active_region_included = False
            if active_rect is not None:
                clipped = _clamp_rect(
                    active_rect,
                    mon.get("left", 0), mon.get("top", 0),
                    mon["width"], mon["height"],
                )
                if clipped is not None:
                    x0, y0, w, h = clipped
                    phash_img = img.crop((x0, y0, x0 + w, y0 + h))
                    active_region_included = True

            full_phash = _dhash(img, hash_size=16)
            # A 64-bit hash is too coarse for a few newly typed terminal
            # characters. Match the full-frame hash resolution so small text
            # changes survive downsampling.
            phash = _dhash(phash_img, hash_size=16)
            jpeg = _encode_jpeg(img, quality=80, max_dim=1600)
            return Screenshot(
                width=img.width,
                height=img.height,
                jpeg_bytes=jpeg,
                phash=phash,
                full_phash=full_phash,
                capture_bounds=(
                    mon["left"], mon["top"],
                    mon["left"] + mon["width"], mon["top"] + mon["height"],
                ),
                display_id=mon.get("unique_id"),
                active_region_included=active_region_included,
            )
    except Exception as e:
        if not _warned_full_error:
            log.warning("full-screen capture failed: %s", e)
            _warned_full_error = True
        return None
