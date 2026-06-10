# Privacy

GuardianNode is built around one promise: **your child's data does not leave machines you control.**

## What we collect

GuardianNode collects two kinds of data:

1. **Activity events** from the child's PC — but only from monitored apps and approved browser domains:
   - Visible text extracted via OCR (native apps) or DOM reading (web)
   - URLs, page titles, app/window names
   - Clipboard text (optional, off by default)
   - Image hashes for downloaded files (optional)

2. **Risk results** computed locally by the Ollama LLM:
   - Risk severity (none/low/medium/high/critical)
   - Categories triggered
   - A short summary
   - Confidence score

## What we do NOT collect

- ❌ Raw system-wide keystrokes
- ❌ Audio from the microphone
- ❌ Webcam video
- ❌ Content from non-monitored apps (unless the parent opts into full-screen capture)
- ❌ Banking / payment data and other secrets (redacted before classification by the secret-pattern filter)
- ❌ Anything when the parent has triggered "pause monitoring"

## Where data goes

- **All-in-one mode**: Stays on the single PC. Backend binds to `127.0.0.1` by default — nothing leaves the loopback interface.
- **Separated mode**: Child PC ➝ Parent server (over your LAN, optionally TLS). Nothing leaves your home network.
- **Cloud**: 🚫 GuardianNode does not call any cloud API. No telemetry. No crash reporting. No model API calls. No A/B testing.

Verify this yourself: the backend has zero outbound network code other than (a) optional SMTP for parent-configured notifications and (b) the parent-controlled Ollama server URL (defaults to localhost).

## Encryption

- Sensitive event fields (redacted text, screenshots, file paths) are encrypted at rest with **AES-256-GCM**.
- The master key is generated locally on first run and never leaves the machine.
- The 12-word recovery code derives the master key via PBKDF2/HKDF.
- On Windows, the key is additionally wrapped with **DPAPI** so even root file-system access doesn't decrypt without the parent password.

## Retention defaults

| Data type | Default retention | Configurable |
|---|---|---|
| Critical/high alerts | 90 days | ✅ |
| Medium alerts | 30 days | ✅ |
| Low/no-risk events | 24 hours or not stored | ✅ |
| Flagged screenshots | 30 days | ✅ |
| Raw OCR cache (unflagged) | 24 hours | ✅ |
| Audit logs | 180 days | ✅ |

You can wipe any of this from the dashboard at any time. Wipes are real (overwrite + vacuum), not soft-delete.

## Transparency to the child

GuardianNode is **not** stealth software:
- A visible tray icon shows when monitoring is active
- The agent is listed in Programs & Features and Task Manager — it is not hidden
- The child can see paused state
- We recommend you tell your kid that monitoring is in place and why; the audit log helps you have an honest conversation

If you need stealth/spyware behavior, GuardianNode is not the right tool. We will not add that capability.

## Children's data and applicable laws

- **COPPA (US)**: GuardianNode is operated by the parent, not by a third party. It does not transmit children's data to any operator. The parent is the data controller.
- **GDPR (EU/UK)**: Same principle — the parent is the data controller; GuardianNode is a tool, not a service.
- **State-level US laws (NY SHIELD, CCPA, etc.)**: Same.

If you intend to deploy GuardianNode at scale (e.g. school district, foster-care org), consult your jurisdiction's data-protection authority. This is family-scale software by design.

## Sharing data with anyone

If you decide to share an alert or evidence with law enforcement, a school counselor, or a therapist:
- The dashboard provides an **Export** button that produces a signed, encrypted ZIP.
- You and only you can decide what to export and to whom.
- We do not auto-report to anyone — not law enforcement, not platforms, not us.

## Questions

Open an issue on GitHub with the `privacy-question` label, or email `privacy@guardiannode.example`.
