# Devpost Submission Draft

## Project name

GuardianNode — Guardian Review

## One-line tagline

A local-first family safety monitor that lets a parent preview a privacy-minimized GPT-5.6 second opinion and turn an alert into a calmer conversation.

## Track

Apps for Your Life

## Problem

Parents can face alarming fragments of online activity without enough context.
A keyword or screenshot may matter, may be a joke, or may be school research.
An unexplained “high risk” label can provoke an accusation when the family first
needs careful fact-finding, immediate safety separation, and proportionate next
steps.

## Solution

GuardianNode detects risk locally on a Windows device the parent owns or
administers. Guardian Review is an optional Build Week extension: the parent
opens an existing incident, supplies coarse relationship/context information,
reviews the exact minimized text proposed for external processing, and chooses
whether to continue. GPT-5.6 returns a strict assessment that separates observed
facts from inference, surfaces uncertainty and benign explanations, and creates
a practical, non-accusatory conversation plan. The parent remains the final
decision-maker; the model cannot punish, block, contact, diagnose, or make legal
conclusions.

## How it works

1. The visible Windows agent captures configured screen evidence.
2. The parent-owned backend encrypts evidence and runs deterministic/local
   detectors and optional local Ollama models.
3. A normalized local risk creates a dashboard incident.
4. Guardian Review loads that authorized incident server-side; it never trusts
   a browser-supplied incident payload.
5. Deterministic minimization removes paths, device/account identifiers,
   emails, phones, handles, URLs, precise locations, and unrelated context.
6. The parent sees the exact outbound JSON, can remove optional fields, and must
   explicitly consent.
7. The server-side Responses API request uses configurable `gpt-5.6`,
   `store: false`, no tools, and strict schema `1.1.0`.
8. The encrypted local result presents uncertainty, actions, and a conversation
   plan; versioned parent feedback remains local.

## Existing-project / Build Week disclosure

The immutable pre-Build Week baseline is tag `pre-build-week-2026`, commit
`36b2a547056d40eff32f00aa59b7820f7d3e98d5`. It already contained the Windows
agent, FastAPI backend, React dashboard, local detection, encrypted evidence,
authentication/security controls, installers, and 353 passing unique tests.

Guardian Review is the Build Week extension: its service, strict schema,
GPT-5.6 provider, minimizer and consent preview, durable persistence, complete
parent communication UI, feedback, six-scenario judge demo, 55-case evaluation,
and related reliability/privacy hardening were added after that tag. The owner
describes portions of the pre-existing visual web UI as Claude-assisted and the
pre-existing agent/backend/platform work as Codex-built; Git cannot completely
verify assistant attribution.

## How Codex was used

Codex preserved and tagged the baseline, traced the real incident path, defined
the schema/privacy contract, implemented backend and UI changes, wrote tests and
synthetic fixtures, ran release and security audits, fixed the findings, and
assembled reproducible submission evidence. Important human decisions included
keeping cloud review opt-in, binding consent to exact bytes and versions,
keeping feedback local, refusing diagnostic/enforcement claims, and disabling a
convenient coding-agent transport when its capability boundary was not safe
enough for family incident evidence.

## How GPT-5.6 was used

During development, GPT-5.6-powered Codex accelerated repository analysis,
implementation, verification, and documentation. At runtime, Guardian Review's
direct OpenAI Responses API path defaults to `gpt-5.6` and returns only the
versioned strict assessment object. The request sets `store: false`, supplies no
tools, and is blocked unless the operator explicitly confirms the configured
project's approved Zero Data Retention controls. We do not claim that
`store: false` alone guarantees zero retention.

An experimental “Sign in with ChatGPT” Codex path was evaluated using only
synthetic data. We disabled it after adversarial review because a coding agent
can have local read tools. Parent-friendly subscription integration remains a
goal, but it must first provide enforceable zero-tool isolation.

## Challenges

- Minimizing enough context to protect privacy without removing the facts that
  make an incident understandable.
- Designing a strict schema that is useful for a worried parent without
  presenting an AI assessment as fact.
- Making consent meaningful and resistant to stale previews, duplicate clicks,
  refreshes, timeouts, and restarts.
- Being honest about model limits: a deterministic mock is excellent for the
  judge path but not evidence of nuanced judgment, and a small synthetic live
  sample is not a universal accuracy claim.

## Accomplishments

- Complete incident → preview → consent → strict assessment → encrypted local
  persistence → communication plan → parent feedback path.
- Six resettable synthetic judge scenarios, usable in mock mode without real
  family data or an API key.
- Fifty-five synthetic evaluation cases across concerning, ambiguous, benign,
  missing-context, false-positive, quoted/research/gaming/medical, and
  prompt-injection groups.
- Explicit auth, CSRF, authorization/IDOR, timeout, retry, malformed output,
  audit leakage, redaction bypass, XSS, and failure-recovery tests.
- A security-driven decision to fail closed rather than ship a more convenient
  but overly capable provider transport.

## What we learned

The most important output is often not a risk label. Parents need a clear split
between facts and inference, plausible benign explanations, what remains
unknown, and words that help preserve trust. Privacy also needs product UX:
local redaction alone is not meaningful consent unless the parent can inspect
and control the exact outbound content.

## Next steps

- Qualify the unsigned Windows release candidate on fresh Windows 11 hardware,
  including reboot, uninstall, reinstall, firewall, and failure recovery.
- Expand international identifier/location minimization and independent human
  review of the evaluation rubric.
- Add a genuinely consumer-friendly OpenAI connection only when it can enforce
  a zero-tool privacy boundary.
- Conduct opt-in beta onboarding with synthetic-first support and no silent
  behavior changes from individual feedback events.

## Repository and judge instructions

1. Read `README.md` and `docs/build-week/BASELINE.md` for the exact prior/new
   split.
2. For a no-key demo, enable Guardian Review and demo mode with provider `mock`.
3. Open **Synthetic demo**, select a scenario, trigger it, open the incident,
   inspect the outbound preview, consent, review guidance, save feedback, reset.
4. Run `python -m app.guardian_review_evaluation --provider mock` from
   `backend/` for machine-readable results.

GuardianNode is AGPL-3.0 alpha software. It can miss risks or create false
positives; it is not an emergency, diagnostic, legal, or substitute-parenting
service.
