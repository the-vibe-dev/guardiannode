# GuardianNode 0.1.0-alpha.2 — Build Week release candidate

GuardianNode remains alpha software for technical parents, developers, and
safety reviewers. This candidate adds Guardian Review to the existing
local-first Windows agent, parent-owned backend, local detection, encrypted
evidence, dashboard, and installer foundation.

## Guardian Review

- Parent-requested second opinion on an authorized existing incident.
- Deterministic minimization/redaction v3 and exact outbound-data preview.
- Explicit digest-bound consent for each live request.
- Server-side OpenAI Responses API with configurable `gpt-5.6`, `store: false`,
  no tools, strict schema `1.1.0`, bounded timeout, and selective retries.
- Durable encrypted local assessment history, deletion, sanitized audit events,
  complete parent communication guidance, and versioned local feedback.
- Six resettable synthetic demo scenarios and a 55-case synthetic evaluation.
- Deterministic mock mode that needs no API key or network connection.

The experimental Codex/ChatGPT subscription provider is disabled in this
candidate. Security testing showed that a coding agent's local tools are not an
appropriate boundary for untrusted incident evidence. Direct Responses API and
mock modes remain available.

## Privacy and safety boundaries

Guardian Review is disabled until configured. Local detection never depends on
it. A live request cannot start until the parent sees the exact minimized JSON
and explicitly continues. API keys stay in the backend service environment and
are never embedded in the installer or browser. `store: false` is not claimed
as a zero-retention guarantee; direct live mode requires operator confirmation
of approved Zero Data Retention controls.

The result is advisory. It must not be treated as established fact, diagnosis,
legal conclusion, punishment decision, or emergency service.

## Candidate artifacts

The final Build Week tag is `guardian-node-build-week-2026-final`. Pushing that
tag starts the Windows installer workflow and creates a draft prerelease only
after the workflow's source, test, bundle, and checksum gates pass. The earlier
`guardian-node-build-week-2026` candidate is retained as immutable evidence of
a CI-only readiness-test dependency found before artifacts were published.

The release workflow is expected to produce these unsigned Windows
x64-compatible artifacts:

- `GuardianNodeChildSetup-0.1.0-alpha.2.exe`
- `GuardianNodeServerSetup-0.1.0-alpha.2.exe`
- `SHA256SUMS.txt`

Do not use an artifact unless its workflow completed successfully and its
SHA-256 value matches the release checksum file. This document intentionally
does not invent checksums before the artifacts exist.

The submission source also includes a disposable mock-only recording server,
2:48 voiceover, captions, shot manifest, Codex computer prompt, YouTube copy,
and a read-only final video duration/checksum helper. Video upload and clean
Windows-node qualification remain manual gates.

## Supported scope

- Windows 11 x64: promoted technical-parent client/install qualification target.
- Windows 10: source/qualification target, not promoted.
- Windows or Linux backend from source: technical evaluation.
- Separated deployments: trusted private LAN/VPN/TLS only.
- Direct public-internet exposure: unsupported.

Installers are unsigned and may trigger SmartScreen or antivirus warnings.
Windows clean-install, reboot, uninstall, and reinstall results must be recorded
against the exact candidate artifacts before beta promotion.

## Upgrade

Back up the database and export a portable encryption-key backup before an
upgrade. The backend applies additive database migrations at startup. Keep the
existing data directory and do not replace its encryption keys. Review the
sample environment file for new Guardian Review flags; it remains disabled by
default.

## Known limitations

- OCR and local-model accuracy/performance depend on content and hardware.
- Deterministic redaction is defense-in-depth, not a proof of anonymity.
- The 55-case evaluation uses synthetic expected properties, not clinical or
  universal accuracy ground truth.
- Live GPT-5.6 mode is an advanced server configuration and incurs provider
  processing/cost under the configured account.
- Installers are unsigned; release-candidate hardware qualification is manual.
- GuardianNode can miss risks or produce false positives and must not be the
  family's only safety measure.
