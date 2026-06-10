# OCR

The agent extracts text from monitored apps via OCR.

## Engines

- **Primary**: PaddleOCR (Apache-2.0, accurate, ~300 MB)
- **Fallback**: Tesseract (Apache-2.0, smaller, ~50 MB)
- **None**: no classical OCR — the vision LLM reads text directly from the screenshot

Configurable: `OCR_ENGINE=paddle|tesseract|none`

## Pipeline

```
Active monitored app
  ↓
Capture active-window screenshot
  ↓
Perceptual hash diff (skip if unchanged)
  ↓
Crop app-specific region if known
  ↓
Resize / grayscale / contrast (OpenCV)
  ↓
Run OCR
  ↓
Normalize whitespace
  ↓
Deduplicate (don't resend identical lines)
  ↓
Redact secrets
  ↓
POST /api/events
```

## OCR cadence

- High-risk active apps (Roblox, Discord): every 2–5 seconds
- General monitored apps: every 10–20 seconds
- Foreground only — background windows are skipped

## App-specific crop regions

Config in `agent-windows/ocr_regions/` per app:

```yaml
app: Roblox.exe
regions:
  chat_left:
    x_pct: 0.01
    y_pct: 0.10
    w_pct: 0.45
    h_pct: 0.55
```

Tunes accuracy and speed for known UIs.

## Dedupe

Per-app rolling cache of recently seen lines (LRU 200 entries). Identical lines within 60s are dropped.

## Confidence

Each OCR result includes the engine's confidence. Below `OCR_MIN_CONFIDENCE` (default 0.5), the event is dropped to reduce noise.

## Privacy

OCR text is redacted before storage. Screenshots are NOT stored unless the event becomes a flagged alert; even then they're encrypted.
