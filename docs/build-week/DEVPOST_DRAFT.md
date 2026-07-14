# Preliminary Devpost Draft

> Draft status: July 14 implementation content. Parent alert-page presentation,
> feedback, and expanded judge evaluation remain incomplete.

## Project

GuardianNode is a local-first, open-source safety monitor that helps parents
review risk signals from a Windows device they own or administer. Screenshots,
OCR, deterministic rules, optional local Ollama classifiers, encrypted evidence,
and the parent dashboard already existed before Build Week.

## What Build Week adds

Guardian Review is the implemented opt-in backend second-opinion layer. A parent can
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

## How GPT-5.6 is used

The direct OpenAI Responses API provider defaults to `gpt-5.6`, sends only
locally minimized/redacted text, requires preview and consent, uses strict
schema `1.1.0` and `store: false`, and fails closed unless ZDR is confirmed. The
parent-friendly provider uses the official Codex CLI, “Sign in with ChatGPT,”
and `gpt-5.6-sol`; it discloses that ChatGPT plan/workspace controls apply.
Model output is guidance, never an enforcement input.

## Architecture

Windows agent → local FastAPI backend → local detectors/models → encrypted
evidence and alert → parent dashboard → local minimization/redaction → exact
outbound preview/consent → asynchronous Guardian Review → strict structured
result → parent feedback and local audit.

## Current backend demo

1. Show a healthy synthetic Windows device.
2. Generate a synthetic incident.
3. Show local detection and persisted alert in the dashboard.
4. Run the synthetic Guardian Review harness in deterministic mock mode or an
   explicitly confirmed Codex live mode.
5. Inspect the exact outbound preview and digest-bound consent record.
6. Process the durable job and retrieve the strict assessment.
7. Verify the encrypted local result and privacy-preserving audit trail.

The alert-page preview/result display and Guardian Review-specific feedback are
the next UI step. The offline judge path uses deterministic mock mode. A live
Codex demonstration uses only synthetic data and discloses ChatGPT workspace
controls; a direct API live step requires ZDR.

## Current limitations

GuardianNode is alpha software and can miss risks or create false positives.
Windows 11 x64 is the current promoted client path. Installers are unsigned.
OCR/local-model results depend on hardware and content. Guardian Review remains
a fallible second opinion rather than a diagnosis or emergency response. The
Codex device-login UI has not yet been qualified on a Windows installer build,
and the direct live API path was not exercised without an API key.

## License

GuardianNode is released under AGPL-3.0, with third-party and model license
notices included in the repository.
