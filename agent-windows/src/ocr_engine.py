"""Pluggable OCR.

Engines:
- tesseract — requires pytesseract + the tesseract binary
- paddle    — requires paddleocr (heavy)
- none      — agent runs without OCR

Falls back gracefully if a dependency is missing.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float


class OCREngine(Protocol):
    def recognize(self, png_bytes: bytes) -> OCRResult: ...


class NoneEngine:
    def recognize(self, png_bytes: bytes) -> OCRResult:
        return OCRResult(text="", confidence=0.0)


class TesseractEngine:
    def __init__(self) -> None:
        import pytesseract  # noqa: F401  (ensure available)
        from PIL import Image  # noqa: F401

    def recognize(self, png_bytes: bytes) -> OCRResult:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(png_bytes))
        text = pytesseract.image_to_string(img)
        # tesseract doesn't easily give per-image confidence — estimate from word data
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confs = [int(c) for c in data.get("conf", []) if c not in ("", "-1")]
            confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.5
        except Exception:
            confidence = 0.5
        return OCRResult(text=text.strip(), confidence=confidence)


class PaddleEngine:
    def __init__(self) -> None:
        from paddleocr import PaddleOCR  # type: ignore
        self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

    def recognize(self, png_bytes: bytes) -> OCRResult:
        import numpy as np
        from PIL import Image
        img = np.array(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
        result = self._ocr.ocr(img, cls=True)
        if not result or not result[0]:
            return OCRResult(text="", confidence=0.0)
        lines, confs = [], []
        for line in result[0]:
            try:
                txt = line[1][0]
                conf = float(line[1][1])
                lines.append(txt)
                confs.append(conf)
            except Exception:
                continue
        text = "\n".join(lines)
        confidence = (sum(confs) / len(confs)) if confs else 0.5
        return OCRResult(text=text.strip(), confidence=confidence)


def make_engine(name: str) -> OCREngine:
    if name == "none":
        return NoneEngine()
    if name == "tesseract":
        try:
            return TesseractEngine()
        except Exception as e:
            log.warning("tesseract unavailable (%s); OCR disabled", e)
            return NoneEngine()
    if name == "paddle":
        try:
            return PaddleEngine()
        except Exception as e:
            log.warning("paddleocr unavailable (%s); falling back to tesseract", e)
            try:
                return TesseractEngine()
            except Exception:
                return NoneEngine()
    return NoneEngine()
