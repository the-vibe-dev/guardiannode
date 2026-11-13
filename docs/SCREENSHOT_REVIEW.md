# Screenshot capture and AI review

GuardianNode focuses on one workflow: capture permitted visible screen content,
review it with local OCR, rules and optional AI, then give a parent understandable
evidence and a useful review workflow. It does not impose screen-time limits,
block websites or apps, suspend a child's programs, or offer exception requests.

## What the product does

1. A visible Windows capture process samples the configured desktop region.
   The present full-screen mode covers the primary display. App-scoped capture
   limits which foreground contexts are collected; it does not stop those apps
   from running.
2. The broker stores eligible frames in an encrypted, bounded retry queue and
   uploads them to the parent-owned backend over the configured trusted transport.
3. The backend records acceptance, then performs OCR, deterministic rules and
   the selected local model pipeline. Acceptance and completion are separate
   stages. A model failure must not be presented as a successful AI review.
4. Policy determines which findings create alerts and which alerts notify the
   parent. These are review thresholds, not device controls.
5. Parents can reveal retained evidence, read the reasoning and uncertainty,
   add notes, mark a false positive, confirm a useful alert, dismiss or escalate
   their review, and delete evidence through the audited deletion workflow.
6. Optional Guardian Review offers a separate external-model second opinion on
   the exact minimized text the parent previews and explicitly approves. Raw
   screenshots are not silently sent to that provider.

The **Home** page is the capture/review overview; **Risk Feed** is the triage
queue; an **Alert** contains the evidence and assessment. **Models** and
**Settings** diagnose processing, delivery, queue and storage health.

## Reading status accurately

A recent device heartbeat proves connectivity. A capture receipt proves that
this server accepted a frame. A completed review proves that the configured
processing path produced a record. These facts are distinct.

Check each device, including its last receipt, most recent processing result,
and the reported model/rules status. Rules-only operation can still flag known
text patterns, but it is not successful AI vision analysis. Missing or stale
telemetry means unknown coverage. A global healthy result from one device does
not demonstrate that every device is being captured.

The queue's estimated wait depends on recent observed latency and is an
estimate, not a deadline. Its transient counters reset or become unknown after
restarts and stale heartbeats. Consult the per-device status and diagnostics
rather than interpreting an empty queue as proof that every visible screen was
reviewed. No alert is not a finding that an interaction was safe.

## Capture and review quality

Screenshots are samples, not a video recording. Brief content between samples,
secondary displays, secure desktops and content on other devices may be missed.
Small fonts, scaling, image compression, theme, language and the configured
model affect what can be read. The first eligible frame after a monitoring pause
or capture-scope change is sampled anew rather than suppressed as an unchanged
pre-pause frame.

The local classifier's score and confidence are model/rule estimates. They are
not measured accuracy percentages. Review the screenshot and surrounding
context before reaching a conclusion. A parent marking an alert useful or a
false positive records feedback; it does not prove that a model has been trained
or automatically recalibrated.

## Privacy controls stay part of capture

Screenshot monitoring can be paused or disabled. This stops collection, not use
of the child's computer. Consent, metadata choices, access control, evidence
retention, deletion and external-review preview remain in place.

Retention periods, bounded queues, upload sizes and processing concurrency
protect local storage and runtime reliability. They are not screen-time limits
or restrictions on browsing. Full screenshots can contain sensitive visible
content; encrypting them is not the same as redacting them. There is no
unqualified guarantee that passwords, private messages or identifiers are
removed from image pixels.

## Upgrade from a restriction-enabled build

The matching backend rejects new restriction and child-notice commands. The
Windows agent has a release-only compatibility component for older GuardianNode
journals. It can release a verified owned suspension and remove owned legacy
hosts entries; it cannot create a new restriction. Historical action receipts
remain for audit and recovery, and old exception data is retained for compatible
reads rather than used as an active approval workflow.

Read [legacy restriction recovery](ENFORCEMENT.md) before upgrading an existing
installation. Install the matching backend, dashboard and Windows agent together.
An old endpoint that is offline cannot receive a change immediately.

## Next improvements in scope

- Native Windows capture qualification across DPI, multiple displays, session
  changes, sleep/resume and degraded networks.
- Representative OCR and vision evaluation with published errors by category,
  language and environment; benchmark the actual installed model and hardware.
- Durable end-to-end capture, drop, retry and review-latency diagnostics.
- Optional capture exclusions or masking with clear coverage tradeoffs.
- More useful incident grouping, evidence navigation and parent feedback analysis.
- Signed installers, qualified upgrades and local model recovery.

See the [roadmap](ROADMAP.md) and included review report for the ordered backlog.
