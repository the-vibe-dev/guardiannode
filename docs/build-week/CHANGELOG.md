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
