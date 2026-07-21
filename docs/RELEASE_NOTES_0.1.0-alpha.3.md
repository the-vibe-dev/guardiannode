# GuardianNode 0.1.0-alpha.3 — Build Week qualified candidate

GuardianNode remains alpha software for technical parents, developers, and
safety reviewers. This candidate contains the complete Guardian Review Build
Week extension from `0.1.0-alpha.2` plus one real-Windows qualification fix.

## Windows qualification correction

Clean unattended testing on a current Windows 11 GPU node found that Ollama's
interactive scheduled task can register successfully from an SSH/service
session without becoming runnable until the next desktop logon. The installer
previously waited for that task and failed before installing GuardianNode.

The bootstrap now keeps the persistent logon task, waits briefly for it, and
starts a direct installer-session fallback when the task is not reachable. The
fallback is used only to complete prerequisite/model setup; the registered task
remains the persistent startup path at interactive logon. This behavior is
covered by release-script tests and was reproduced successfully on the Windows
qualification node before rebuilding the candidate.

## Guardian Review

- Parent-requested second opinion on an authorized existing incident.
- Deterministic minimization/redaction v3 and exact outbound-data preview.
- Explicit digest-bound consent for each live request.
- Server-side OpenAI Responses API with configurable `gpt-5.6`, `store: false`,
  no tools, strict schema `1.1.0`, bounded timeout, and selective retries.
- Durable encrypted local assessment history, deletion, sanitized audit events,
  parent communication guidance, and versioned local feedback.
- Six resettable synthetic scenarios, a 55-case synthetic evaluation, and a
  deterministic mock mode requiring no API key or family data.

The experimental Codex/ChatGPT subscription provider remains disabled. A
coding agent's local tools are not an appropriate execution boundary for
untrusted incident evidence. Direct Responses API and mock modes remain
available.

## Privacy and safety boundaries

Guardian Review is disabled until configured. Local detection never depends on
it. A live request requires exact minimized-context preview and explicit parent
consent. API keys remain server-side. `store: false` is not presented as a
zero-retention guarantee, and live mode requires operator confirmation of the
configured OpenAI project's retention controls.

Guardian Review is advisory. It does not establish truth, diagnose a condition,
make a legal conclusion, decide punishment, or replace emergency assistance.

## Candidate artifacts

The final qualification tag creates a draft prerelease only after source,
tests, Windows bundles, and checksum gates pass. Expected unsigned artifacts:

- `GuardianNodeChildSetup-0.1.0-alpha.3.exe`
- `GuardianNodeServerSetup-0.1.0-alpha.3.exe`
- `SHA256SUMS`
- `release-manifest.json`

Verify the exact SHA-256 values from the generated checksum file before use.
The installers are unsigned and may trigger Defender or SmartScreen warnings.

## Supported scope

- Current Windows 11 x64: technical-parent client/install target.
- Windows 10: unpromoted qualification target.
- Windows or Linux backend from source: technical evaluation.
- Separated deployments: trusted private LAN/VPN/TLS only.
- Direct public-internet exposure: unsupported.

## Known limitations

- OCR and local-model behavior depends on content and hardware.
- Deterministic redaction is defense-in-depth, not proof of anonymity.
- Synthetic evaluation does not establish clinical or universal accuracy.
- Live GPT-5.6 mode is an advanced server configuration and requires an
  eligible account, server-side key, and verified retention controls.
- Installers are unsigned.
- GuardianNode can miss risks or create false positives and must not be the
  family's only safety measure.
