# Image Safety

Detects nudity, gore, weapons, drugs, self-harm imagery, hate symbols, private info visible on screen, suspicious QR codes, phishing screenshots.

## Pipeline

```
Screenshot / image
  ↓
OpenCV preprocessing (resize, normalize)
  ↓
Optional first-pass classifier (NSFWJS plugin) — fast filter
  ↓
OCR text extraction → forwarded to text classifier
  ↓
Vision LLM (Ollama llava / llava-phi3) — only if triggered
  ↓
Multimodal merge with text classifier
  ↓
Encrypted blob storage if flagged
  ↓
Alert
```

## When the vision LLM runs

Not on every screenshot — it's expensive. It runs when:
- The text OCR result is already medium+
- New image appears in Downloads (file watcher)
- Clipboard contains an image
- Parent manually requests review
- Periodic sample interval (default 15–30s for image-heavy apps)

## Prompt

`backend/app/prompts/vision_classifier.txt`. Returns strict JSON:

```json
{
  "risk_level": "none|low|medium|high|critical",
  "score": 0,
  "categories": ["nudity", "weapons", ...],
  "summary": "...",
  "visual_evidence": ["..."],
  "recommended_action": "...",
  "confidence": 0.0,
  "false_positive_notes": ""
}
```

## Storage

- Original image is **never** stored unencrypted
- AES-GCM encrypted blob in `evidence/<sha256-prefix>/<sha256>.enc`
- Decrypted only on parent dashboard view, audited
- Default 30-day retention; configurable

## Models

- Tiny: `moondream` (~1.8GB)
- Small: `llava-phi3` (~2.4GB)
- Medium: `llava:7b` (~4.5GB)
- Large: `llama3.2-vision:11b` (~7.5GB)

## Adversarial input

Treat vision LLM output as a hint, not ground truth. Combine with rules engine, text classifier, and (for the parent) the actual evidence.
