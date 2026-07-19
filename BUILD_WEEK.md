# GuardianNode Build Week 2026

GuardianNode entered Build Week at `2026-07-13 00:00 America/New_York`.
The last repository commit before that cutoff is
`36b2a547056d40eff32f00aa59b7820f7d3e98d5`, protected by the annotated tag
`pre-build-week-2026`. Implementation was developed on
`build-week/guardian-review` and `build-week/guardian-review-privacy`; the
submission comparison is the immutable baseline against `main`.

This file is the concise disclosure. Detailed evidence lives under
[`docs/build-week/`](docs/build-week/BASELINE.md).

## Existing before Build Week

- A visible Windows child-device agent with screenshot capture, pairing,
  heartbeats, a durable local upload queue, watchdog, and tray/status UI.
- A parent-owned FastAPI backend with local OCR, deterministic rules, optional
  Ollama text/vision classification, encrypted evidence, SQLite persistence,
  alerting, retention, notifications, recovery, and audit logging.
- A React parent dashboard for setup, devices, profiles and policy, model
  status, risk feed, alert evidence, alert review/feedback, settings, and audit.
- Windows and Linux installer/deployment paths, Docker support, release
  automation, and an existing `v0.1.0-alpha.1` prerelease.
- Authentication controls including one-time setup, password sessions, CSRF,
  recent/critical step-up authentication, recovery codes, device tokens,
  host validation, and rate limiting.
- 353 unique automated tests passing in the practical Linux baseline run.

The repository owner describes the existing dashboard/visual UI as
Claude-assisted and the existing agent, backend, security, installer, and
platform hardening as Codex-built. Git history does not contain enough
consistent attribution metadata to independently prove that complete split.

## Added during Build Week

- A verifiable baseline tag and dedicated Build Week branch.
- Build Week evidence, privacy, evaluation, collaboration, and submission
  documents.
- A versioned, machine-readable Guardian Review assessment schema.
- A submission-focused README shell and repository public-readiness audit.
- A dedicated durable Guardian Review service, encrypted preview/result models,
  migration, worker, authorization, audit events, deduplication, and deliberate
  fresh-assessment path.
- Strict schema `1.1.0` with explicit observed-fact/inference separation and
  prompt version `guardian-review-v2`.
- Server-authoritative incident loading, local minimization/redaction, exact
  outbound preview, digest-bound consent, and sanitized failure handling.
- Deterministic mock and optional direct OpenAI Responses API providers. Direct
  API requests use model alias `gpt-5.6`, `store: false`, no tools, strict
  Structured Outputs, and a ZDR hard gate.
- A security review that disabled the experimental ChatGPT-authenticated Codex
  transport after its local coding tools proved unsuitable for untrusted
  family incident evidence.
- A synthetic developer harness. A live synthetic Codex run completed through
  `gpt-5.6-sol` and encrypted local persistence on July 14 before that transport
  was disabled.
- Exact parent-controlled outbound preview/consent, structured communication
  guidance, encrypted local assessment history/deletion, and versioned local
  feedback.
- Six resettable synthetic judge scenarios, a guided under-five-minute flow,
  and a 55-case machine-readable evaluation harness.
- Release hardening, synthetic screenshots, submission validation, Devpost
  copy, and the Codex-computer video production package.

## Remaining external qualification

- Run the exact Windows candidate on a clean real node, including reboot,
  uninstall, reinstall, firewall, agent enrollment, and failure recovery.
- Record and publicly verify the under-three-minute YouTube video.
- Run `/feedback`, preserve the session ID privately, and submit Devpost.

## Evidence index

- [Baseline](docs/build-week/BASELINE.md)
- [Build Week changelog](docs/build-week/CHANGELOG.md)
- [Codex collaboration](docs/build-week/CODEX_COLLABORATION.md)
- [Guardian Review specification](docs/build-week/GUARDIAN_REVIEW_SPEC.md)
- [Privacy model](docs/build-week/PRIVACY_MODEL.md)
- [Evaluation plan](docs/build-week/EVALUATION_PLAN.md)
- [Submission checklist](docs/build-week/SUBMISSION_CHECKLIST.md)
- [Final Devpost draft](docs/build-week/DEVPOST_DRAFT.md)
- [July 14 daily completion report](docs/build-week/DAILY_2026-07-14.md)
- [Final submission review](docs/build-week/FINAL_SUBMISSION_REVIEW.md)
- [Video production runbook](docs/build-week/video/VIDEO_PRODUCTION_RUNBOOK.md)
