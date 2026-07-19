# Build Week Changelog

Changes in this file are relative to the immutable `pre-build-week-2026` tag.

## 2026-07-13 — Baseline and submission foundation

Added:

- Verified baseline tag and dedicated Build Week branch.
- Baseline, collaboration, privacy, evaluation, specification, checklist, and
  preliminary Devpost evidence.
- Versioned Guardian Review strict assessment JSON Schema.
- README Build Week disclosure and safe sample environment file.
- Public-readiness audit results and sanitized current release-validation text.

Not yet implemented:

- Guardian Review backend service, database migration, worker, and dashboard UI.
- OpenAI Responses API calls or GPT-5.6 runtime dependency.
- Outbound preview/consent interaction, Guardian Review feedback, synthetic
  judge demo, or evaluation harness.

Future entries must identify the implementation commit, tests, prompt version,
schema version, model configuration, and any privacy-impacting change.

## 2026-07-14 — Guardian Review backend and GPT-5.6 integration

Implemented:

- Schema `1.1.0`, prompt `guardian-review-v1`, encrypted preview/result tables,
  Alembic revision `0003_guardian_reviews`, durable worker, audit events, and
  cascade-safe retention.
- Authoritative alert loading, bounded parent context, coarse age group,
  minimization/redaction, exact preview, expiring digest-bound consent,
  idempotent duplicate handling, and explicit fresh assessments.
- Direct OpenAI Responses API provider using configurable `gpt-5.6`, strict
  `text.format` JSON Schema, `store: false`, no tools, 45-second timeout, and
  at most two attempts for eligible transient failures only.
- ChatGPT-authenticated Codex provider using configurable `gpt-5.6-sol`,
  ephemeral/read-only isolated execution, strict output schema, service-owned
  OAuth storage, and guided device login. API-key mode remains an advanced
  optional provider.
- Deterministic mock provider and `guardiannode-review-harness` synthetic CLI.
- Parent dashboard provider/readiness and “Connect with ChatGPT” flow.

Verified:

- Untouched July 14 baseline: 353 passed, 0 failed, 0 skipped.
- Live synthetic Codex path: completed, schema-valid, encrypted locally,
  requested/returned model `gpt-5.6-sol`, 34,112 ms provider latency.
- An initial explicit `gpt-5.6` Codex probe failed safely because this
  ChatGPT-authenticated CLI accepts the Codex alias `gpt-5.6-sol`; the direct
  Responses provider retains the required `gpt-5.6` API default.

Still planned:

- Alert-page outbound preview/consent/result presentation and Guardian
  Review-specific parent feedback.
- Broader frozen judge-scenario rubric and Windows installer qualification of
  the Codex device-login flow.

## 2026-07-15 — Privacy, redaction, consent, and auditability

Implemented:

- Redaction contract `guardian-review-redaction-v2` with Unicode normalization,
  invisible-control removal, obfuscated identifier handling, incident-scoped
  stable placeholders, path/device/account/location masking, and relevance-aware
  URL minimization.
- A stricter outbound allowlist that excludes screenshots, local incident and
  device/profile IDs, exact scores/counts, classifier state, unselected context,
  and full event text by default. Evidence and total payload sizes are bounded.
- Provider readiness gates, exact provider/retention disclosures, digest binding
  to the redaction contract, and sanitized versioned audit metadata.
- Alert-page guided optional-field controls, separate local/transmitted views,
  exact read-only JSON, unchecked consent, cancel-without-send, result display,
  per-alert history, and global history.
- Parent-controlled deletion that scrubs encrypted preview/context/assessment
  content and provider response identifiers while retaining a minimal audit
  tombstone.
- Alembic revision `0004_guardian_review_privacy` plus backend and dashboard
  privacy, cancellation, deletion, history, authorization, and bypass tests.

Still planned:

- Guardian Review-specific parent feedback/evaluation reporting.
- Expanded international address/identifier coverage and frozen judge scenarios.

## 2026-07-16 — Parent communication coaching and complete UI

Implemented:

- Complete advisory result hierarchy: observed facts, concern rationale,
  benign explanations, unknowns, parent questions, recommended tone, opening
  language, child questions, phrases to avoid, actions, escalation indicators,
  and limitations.
- Age/severity/repetition/relationship/goal-aware guidance through the strict
  schema and versioned prompt contract.
- Local versioned feedback labels: helpful, inaccurate, too alarmist, too
  dismissive, missing context, and needs follow-up.
- Keyboard/focus semantics, live status regions, escaped text-only rendering,
  responsive sections, and tests for consent/result/feedback states.

## 2026-07-17 — Synthetic judge demo and recovery

Implemented:

- Six resettable, visibly synthetic scenarios covering secrecy/platform
  migration, ambiguous gaming language, school research, peer coercion,
  medical/educational discussion, and a harmless control.
- Guided dashboard path from demo health through local detection, incident,
  preview, review, feedback, and reset.
- Durable queued/running states, idempotent duplicate submission, safe failure
  persistence, refresh/restart recovery, bounded screenshot backlog, and
  corruption/error handling.

Manual dependency:

- Build Week credit-request submission is an external account/form action and
  cannot be confirmed from repository evidence; no credentials or form answers
  are stored here.

## 2026-07-18 — Evaluation and adversarial review

Implemented:

- A balanced 55-case synthetic dataset across 11 requested groups, a
  machine-readable scorer, and explicit property-based results.
- Prompt-injection, stored-XSS, authorization, redaction-bypass, oversized
  input, logging, and capability-boundary review.
- Redaction contract v3 for bracket-dot emails, IPv6, and complete Windows
  paths; stale previews automatically fail digest/version validation.
- Fail-closed Codex provider/device-login after identifying that a coding
  agent's local tools are unsuitable for untrusted family incident evidence.
- Local classifier prompt cap/concurrency gate, positive list limits, token
  prefix removal from logs, and demo reset ownership markers.

## 2026-07-19 — Release hardening candidate

Implemented:

- Version `0.1.0-alpha.2`, release notes, configuration/troubleshooting guide,
  clean-install checklist, sample configuration, mock demo data, and checksum
  workflow inputs.
- Correct Tailwind v4 CSS entrypoint so the production dashboard bundle includes
  the complete responsive design system; capture five real synthetic-flow
  screenshots from a disposable backend/browser run.
- Full repository test, type, build, dependency, secret, license/notices, and
  link audits are recorded in the daily report on the exact commit.

Still manual before beta promotion:

- Fresh Windows 11 installer, reboot recovery, firewall behavior, uninstall,
  reinstall, signature, and artifact-checksum qualification.

## 2026-07-20 — Submission freeze

Implemented:

- Final README disclosure, Devpost copy, architecture/privacy/evaluation links,
  and a 2:48 voiceover/shot package with captions, a machine-readable manifest,
  a Codex computer prompt, a production runbook, and a disposable mock-only
  recording server.
- Functionality freeze: only golden-path defects and submission evidence change
  after this entry.

Still external/manual:

- Record and upload the public YouTube video, verify logged-out repository/video
  access, and submit the final Devpost form.

## 2026-07-21 — Final verification shell

Added:

- A deterministic submission-package validator for required disclosures,
  local links, baseline identity, video runtime/assets, and Devpost sections.
- Final claim-to-evidence review, private submission-note template, release/tag
  identity, and exact tomorrow handoff for Windows, video, `/feedback`, and
  Devpost account gates.

External status remains explicit: real-node qualification, a live direct-API
synthetic demonstration, YouTube publication, `/feedback`, and form submission
are not represented as complete until the maintainer performs them.

Verified and published internally as a draft release:

- Merged release commit `62590db1911cb84cf01b27de76ab26f238d003d7`
  and immutable tag `guardian-node-build-week-2026-final`.
- Passed the final GitHub release workflow and produced both versioned Windows
  installers, `SHA256SUMS`, and `release-manifest.json`.
- Downloaded the artifacts and verified both SHA-256 values. The prerelease
  remains draft and the unsigned installers remain unqualified on a real node.
