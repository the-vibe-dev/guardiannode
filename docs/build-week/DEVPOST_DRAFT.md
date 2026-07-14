# Preliminary Devpost Draft

> Draft status: baseline-day content. Guardian Review runtime claims must be
> updated only after implementation and recorded evaluation.

## Project

GuardianNode is a local-first, open-source safety monitor that helps parents
review risk signals from a Windows device they own or administer. Screenshots,
OCR, deterministic rules, optional local Ollama classifiers, encrypted evidence,
and the parent dashboard already existed before Build Week.

## What Build Week adds

Guardian Review is the planned opt-in second-opinion layer. A parent will be able
to add context, inspect the exact minimized/redacted JSON proposed for upload,
consent to that one request, and receive a strict structured assessment with
possible benign explanations, missing context, conversation guidance, actions,
escalation indicators, and limitations.

The local detector still creates the alert. Guardian Review will not silently
upload screenshots, autonomously punish a child, or replace a parent,
professional, or emergency service.

## Existing-project disclosure

The immutable pre-Build Week baseline is tag `pre-build-week-2026`, commit
`36b2a547056d40eff32f00aa59b7820f7d3e98d5`. Build Week work is isolated on
`build-week/guardian-review`. The baseline includes the Windows agent, backend,
dashboard, local detection, evidence storage, installer paths, authentication,
security controls, and 353 passing unique tests.

The owner describes the prior dashboard/visual UI as Claude-assisted and the
prior platform implementation as Codex-built; the repository does not provide
complete machine-verifiable assistant attribution.

## How Codex is used

Codex inspected and protected the baseline, traced the real code path, ran the
test/release/security suite, audited public-repository risks, and helped define
the privacy architecture, API, strict schema, evaluation plan, and submission
evidence. No production child data was used.

## How GPT-5.6 will be used

GPT-5.6 is planned through the OpenAI Responses API for a parent-triggered
Guardian Review. The request will contain only locally minimized/redacted text,
will require per-review preview and consent, will use strict structured output
and `store: false`, and will fail closed unless the OpenAI project has verified
Zero Data Retention. Model output will be guidance, never an enforcement input.

## Architecture

Windows agent → local FastAPI backend → local detectors/models → encrypted
evidence and alert → parent dashboard → local minimization/redaction → exact
outbound preview/consent → asynchronous Guardian Review → strict structured
result → parent feedback and local audit.

## Planned demo

1. Show a healthy synthetic Windows device.
2. Generate a synthetic incident.
3. Show local detection and persisted alert in the dashboard.
4. Add parent context and select supporting evidence.
5. Inspect the exact outbound JSON and explicitly consent.
6. Poll the asynchronous review and display the strict assessment.
7. Show calm parent-child conversation guidance and record feedback.
8. Inspect the privacy-preserving audit trail.

The offline judge path will use deterministic mock mode unless live ZDR
eligibility is verified.

## Current limitations

GuardianNode is alpha software and can miss risks or create false positives.
Windows 11 x64 is the current promoted client path. Installers are unsigned.
OCR/local-model results depend on hardware and content. Guardian Review is not
yet implemented at baseline-day commit and, once implemented, will still be a
fallible second opinion rather than a diagnosis or emergency response.

## License

GuardianNode is released under AGPL-3.0, with third-party and model license
notices included in the repository.
