# Image Safety

Detects nudity, gore, weapons, drugs, self-harm imagery, hate symbols, private info visible on screen, phishing screenshots, and other visual risk signals reported by the configured model. QR-related categories are model/rules signals in this alpha; GuardianNode does not ship a dedicated QR decoder yet.

## Pipeline

```
Screenshot / image
  ↓
Optional Tesseract OCR text extraction → forwarded to text classifier
  ↓
Vision LLM (Ollama qwen3-vl:8b-instruct by default, depending on tier)
  ↓
Multimodal merge with text classifier
  ↓
Encrypted blob storage if flagged
  ↓
Alert
```

## When the vision LLM runs

Vision analysis runs according to the configured classifier tier. In the
vision-only tier, changed screenshots are queued and classified by the local
vision model. In text-only tier, GuardianNode uses Tesseract plus the text
classifier instead.

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

- Text default: `llama3.2:3b`
- Vision default: `qwen3-vl:8b-instruct`
- Full dual-model mode keeps text and vision runtimes hot together and is
  intended for 16+ GB VRAM systems.

## Adversarial input

Treat vision LLM output as a hint, not ground truth. Combine with rules engine, text classifier, and (for the parent) the actual evidence.
