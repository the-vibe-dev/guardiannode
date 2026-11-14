"""Synthetic image tests; these do not qualify a native Windows display."""
import io
import random
from types import SimpleNamespace

import pytest
from PIL import Image

from src import screenshot_capture as capture
from src.broker_protocol import MAX_SCREENSHOT_BYTES


def _screen(monitors, monkeypatch):
    calls = []

    class Screen:
        def __enter__(self):
            self.monitors = monitors
            return self

        def __exit__(self, *_args):
            return False

        def grab(self, region):
            calls.append(dict(region))
            image = Image.new("RGB", (region["width"], region["height"]), (42, 100, 160))
            return SimpleNamespace(size=image.size, rgb=image.tobytes())

    monkeypatch.setattr(capture.mss, "mss", Screen)
    monkeypatch.setattr(capture, "_HAS_MSS", True)
    return calls


def test_primary_display_follows_windows_flag_not_enumeration(monkeypatch):
    monitors = [
        {"left": -800, "top": 0, "width": 1824, "height": 768},
        {"left": -800, "top": 0, "width": 800, "height": 600, "is_primary": False},
        {"left": 0, "top": 0, "width": 1024, "height": 768, "is_primary": True, "unique_id": "local-display-b"},
    ]
    calls = _screen(monitors, monkeypatch)
    shot = capture.capture_full(active_rect=(10, 20, 410, 320))
    assert calls == [monitors[2]]
    assert shot.capture_bounds == (0, 0, 1024, 768)
    assert shot.display_id == "local-display-b"
    assert shot.active_region_included is True


def test_other_display_foreground_is_not_claimed_as_captured(monkeypatch):
    monitors = [
        {"left": -800, "top": 0, "width": 1824, "height": 768},
        {"left": 0, "top": 0, "width": 1024, "height": 768, "is_primary": True},
    ]
    _screen(monitors, monkeypatch)
    shot = capture.capture_full(active_rect=(-750, 20, -200, 500))
    assert shot.active_region_included is False
    assert shot.phash == shot.full_phash


@pytest.mark.parametrize("monitors", [[], [{"left": -800, "top": 0, "width": 1824, "height": 768}]])
def test_missing_physical_display_never_expands_to_desktop_union(monkeypatch, monitors):
    calls = _screen(monitors, monkeypatch)
    assert capture.capture_full() is None
    assert calls == []


def test_backend_without_primary_flag_uses_one_physical_monitor(monkeypatch):
    monitors = [
        {"left": -800, "top": 0, "width": 1824, "height": 768},
        {"left": -800, "top": 0, "width": 800, "height": 600},
        {"left": 0, "top": 0, "width": 1024, "height": 768},
    ]
    calls = _screen(monitors, monkeypatch)
    assert capture.capture_full() is not None
    assert calls == [monitors[1]]


@pytest.mark.parametrize("rect", [(-32000, -32000, -31000, -31000), (50, 20, 50, 300), (200, 300, 100, 250)])
def test_offscreen_and_degenerate_app_bounds_do_not_capture(monkeypatch, rect):
    calls = _screen([{"left": -800, "top": -200, "width": 1824, "height": 968}], monkeypatch)
    assert capture.capture_active(rect) is None
    assert calls == []


def test_window_capture_clips_to_visible_desktop_with_negative_coordinates(monkeypatch):
    calls = _screen([{"left": -800, "top": -200, "width": 1824, "height": 968}], monkeypatch)
    shot = capture.capture_active((-900, -250, -100, 300))
    assert calls == [{"left": -800, "top": -200, "width": 700, "height": 500}]
    assert shot.capture_bounds == (-800, -200, -100, 300)
    assert Image.open(io.BytesIO(shot.jpeg_bytes)).size == (shot.width, shot.height) == (700, 500)


def test_encoded_dimensions_match_resized_jpeg(monkeypatch):
    _screen([{"left": 0, "top": 0, "width": 3840, "height": 2160}], monkeypatch)
    shot = capture.capture_active((0, 0, 3840, 2160))
    assert (shot.width, shot.height) == Image.open(io.BytesIO(shot.jpeg_bytes)).size == (1600, 900)
    assert shot.capture_bounds == (0, 0, 3840, 2160)


def test_high_entropy_square_frame_fits_existing_broker_transport_bound():
    image = Image.frombytes("RGB", (1600, 1600), random.Random(42).randbytes(1600 * 1600 * 3))
    original = io.BytesIO()
    image.save(original, format="JPEG", quality=80, optimize=True)
    assert len(original.getvalue()) > MAX_SCREENSHOT_BYTES
    encoded = capture._encode_jpeg(image)
    assert len(encoded) <= MAX_SCREENSHOT_BYTES
    with Image.open(io.BytesIO(encoded)) as decoded:
        decoded.load()
        assert decoded.size == (1600, 1600)


def test_jpeg_encoder_accepts_an_explicit_low_quality():
    encoded = capture._encode_jpeg(Image.new("RGB", (100, 100)), quality=20)
    assert Image.open(io.BytesIO(encoded)).size == (100, 100)
