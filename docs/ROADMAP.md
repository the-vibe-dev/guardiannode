# Screenshot and AI review roadmap

## Product direction

GuardianNode is a local-first screenshot and AI review tool for families. The
product priority is a reliable, understandable capture-to-review workflow.
Screen-time budgets, schedules, app suspension, website blocking, DNS filtering
and requests to bypass restrictions are outside the product scope.

This direction supersedes the earlier enforcement roadmap. Historical release
notes remain historical evidence, not a list of current capabilities. The
current source is **2026-11-13-review.4**, an alpha/developer preview based on
application version **0.1.0-alpha.3**.

## Current foundation

- Visible Windows capture, explicit monitoring consent and capture pause/resume.
- Primary-display or app-scoped screenshots, change detection and encrypted
  offline buffering.
- Parent-owned backend with OCR, deterministic text rules, optional local
  Ollama vision/text models, and encrypted retained evidence.
- Capture/review status per device, with model failure and rules-only results
  distinguished from successful AI processing.
- Review feed, on-demand screenshot reveal, notes, feedback and optional
  explicitly approved Guardian Review second opinions.
- Decisions tied to the evidence displayed by the matching dashboard; stale
  decisions require a refresh when repeated captures update an open alert.
- Final processing checks reject frames whose consent generation or assigned
  child changed during OCR/AI processing.
- Notification policy, retry state, metadata-only digests, retention, consent
  withdrawal, export, backup and audit history.
- Release-only recovery of recorded restrictions from older installations.

Code present does not mean that the changed build is qualified on native Windows,
Docker or every browser. See [release gates](RELEASE_GATES.md).

## Priority 1: qualify the central workflow

1. Build and test the exact Windows server installer and Windows child-device/all-in-one installer on clean machines. Exercise install,
   pairing, capture, review, privacy pause, withdrawal, upgrade and uninstall.
2. Qualify the corrected primary-monitor selection and DPI/scaling; implement explicit multi-display
   capture with per-display provenance before claiming all-monitor coverage.
3. Measure capture acceptance, OCR, local-model completion, queue delay and
   alert delivery on supported hardware, including sleep, restart and outage.
4. Sign installers and updates, and qualify a complete backup/rollback path.

The repository retains workflows for public alpha installer artifacts. Existing
published artifacts do not include or qualify this changed source automatically.

## Priority 2: improve review quality

1. Build a consented or synthetic representative evaluation set with hard benign
   examples, visual-only cases, conversation context and multiple languages.
2. Publish precision/recall and false-positive/negative rates by category, with
   uncertainty and explicit limits on generalization.
3. Measure OCR legibility at the actual capture resolution, not only on clean
   strings or resized synthetic screens.
4. Improve incident grouping and evidence navigation without hiding escalation
   or automatically carrying old review decisions onto new evidence.
5. Make feedback and threshold tuning understandable; never present raw model
   confidence as validated accuracy.

## Priority 3: better capture privacy and operation

1. Add optional excluded-app/region controls and explain resulting blind spots.
2. Evaluate on-device masking or redaction before upload without silently
   removing the text needed to assess grooming, threats or scams.
3. Persist meaningful per-device coverage/drop counters and classify stale,
   permission-denied, capture-disabled and model-unavailable states separately.
4. Improve local model installation, diagnostics and bounded recovery.
5. Add named additional parent accounts and least-privilege review access.

## Later platform work

macOS, Android and iOS require distinct capture permission and background-runtime
designs. Qualify each platform's actual screenshot coverage before promoting it.
A companion review app can follow once the existing private-network dashboard
and notifications meet the reliability goals.

## Features outside this roadmap

No screen-time budgets or time-of-day device restrictions; no app or website
blocking; no network-filter integrations; no exception-approval workflow. Visible
capture, privacy consent and retention controls remain core product requirements.

No hidden monitoring or raw system-wide keystroke capture is planned. External
processing remains deliberate and explicit. The local core stays open source
under the existing project license.
