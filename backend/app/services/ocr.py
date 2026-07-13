"""Structured Tesseract OCR results and dependency probes."""
from __future__ import annotations

import io
import time
from dataclasses import dataclass
from enum import StrEnum

from app.settings import settings


class OcrStatus(StrEnum):
    OK = "ok"
    NO_TEXT = "no_text"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    PROCESS_FAILED = "process_failed"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    IMAGE_DECODE_FAILED = "image_decode_failed"


@dataclass(frozen=True)
class OcrResult:
    status: OcrStatus
    text: str = ""
    engine: str = "tesseract"
    languages: tuple[str, ...] = ()
    duration_ms: int = 0
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {OcrStatus.OK, OcrStatus.NO_TEXT}


def probe_tesseract(languages: list[str] | None = None, *, enabled: bool | None = None) -> dict:
    required = languages if languages is not None else settings.ocr_language_list
    is_enabled = settings.tesseract_enabled if enabled is None else enabled
    if not is_enabled:
        return {
            "ok": False,
            "status": OcrStatus.DEPENDENCY_UNAVAILABLE,
            "error_code": "ocr_disabled",
            "required_languages": required,
        }
    try:
        import pytesseract  # type: ignore

        version = str(pytesseract.get_tesseract_version())
        available = set(pytesseract.get_languages(config=""))
    except Exception as exc:
        return {
            "ok": False,
            "status": OcrStatus.DEPENDENCY_UNAVAILABLE,
            "error_code": type(exc).__name__,
            "required_languages": required,
        }
    missing = sorted(set(required) - available)
    return {
        "ok": not missing,
        "status": OcrStatus.OK if not missing else OcrStatus.UNSUPPORTED_LANGUAGE,
        "version": version,
        "required_languages": required,
        "missing_languages": missing,
        "error_code": "missing_language_data" if missing else None,
    }


def extract_tesseract(image_bytes: bytes) -> OcrResult:
    started = time.monotonic()
    languages = tuple(settings.ocr_language_list)
    dependency = probe_tesseract(list(languages))
    if not dependency["ok"]:
        return OcrResult(
            status=OcrStatus(dependency["status"]),
            languages=languages,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=dependency.get("error_code"),
        )
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageOps, UnidentifiedImageError  # type: ignore

        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            return OcrResult(
                status=OcrStatus.IMAGE_DECODE_FAILED,
                languages=languages,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_code="invalid_image",
            )

        language = "+".join(languages)

        def read(region: Image.Image) -> str:
            gray = ImageOps.autocontrast(ImageOps.grayscale(region))
            scale = min(3.0, 4800 / max(gray.size))
            if scale > 1:
                gray = gray.resize(
                    (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            return pytesseract.image_to_string(gray, lang=language, config="--psm 6").strip()

        readings = [read(image)]
        if image.width >= image.height * 1.4:
            pane_width = int(image.width * 0.6)
            readings.extend(
                (
                    read(image.crop((0, 0, pane_width, image.height))),
                    read(image.crop((image.width - pane_width, 0, image.width, image.height))),
                )
            )
        merged = "\n".join(dict.fromkeys(value for value in readings if value))
        return OcrResult(
            status=OcrStatus.OK if merged else OcrStatus.NO_TEXT,
            text=merged,
            languages=languages,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        error_name = type(exc).__name__
        status = (
            OcrStatus.DEPENDENCY_UNAVAILABLE
            if error_name in {"TesseractNotFoundError", "ImportError", "ModuleNotFoundError"}
            else OcrStatus.PROCESS_FAILED
        )
        return OcrResult(
            status=status,
            languages=languages,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=error_name,
        )
