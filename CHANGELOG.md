# Screenshot-focused review edition - 13 November 2026

## Review.4

Review build `2026-11-13-review.4` uses the newly supplied
`guardiannode-main (9).zip` and preserves its dependency locks, workflow action
pins and Docker base update. The application version remains `0.1.0-alpha.3`.

- Corrects primary-display selection and capture-context consistency, and
  improves bounded screenshot encoding and queue recovery.
- Preserves text-model provenance when deterministic rules raise a risk finding.
- Rechecks consent generation and device assignment before saving a completed
  screenshot review.
- Binds parent decisions and second-opinion previews to the evidence displayed
  by the matching dashboard; stale evidence requires review before retrying.
- Clears deleted sensitive review content immediately, guards asynchronous
  history loading and improves device status refresh and error handling.
- The local review archive retains the full report, comparison, regression
  evidence and source change patch outside Git.

See [current validation](docs/release-validation/screenshot-review4-2026-11-13.md)
for executed checks and remaining release gates. This source integration does not qualify or include a newly signed
Windows installer.

## Review.3 integration (already present in the input)

Review build `2026-11-13-review.3` is based on the supplied source archive and
preserves the upstream application version `0.1.0-alpha.3`. It is an engineering
source evaluation, not a newly qualified installer release.

The current change removes device restrictions and exception workflows, adds
release-only recovery, strengthens screenshot admission and review diagnostics,
rejects invalid AI assessments, preserves screenshot evidence across source-aware
grouping, and refocuses the dashboard and documentation on evidence review.
See [the integration record](docs/release-validation/screenshot-review-2026-11-13.md)
and [focused roadmap](docs/ROADMAP.md).

---

# Changelog

All notable changes to GuardianNode are documented here.

## [Unreleased]

- Established an immutable Build Week baseline and dedicated Guardian Review
  branch.
- Added Build Week evidence, privacy, evaluation, collaboration, submission,
  and preliminary Devpost documents.
- Added the versioned Guardian Review strict assessment schema and README
  existing-project disclosure.
- Sanitized current release-validation infrastructure labels and added a safe
  sample environment file.

Guardian Review runtime, UI, and OpenAI integration remain planned rather than
implemented in this entry.

## [0.1.0-alpha.1] - 2026-06-19

Initial public alpha/developer-preview release.

Includes:

- Windows agent foundation
- Local backend
- Parent dashboard
- Ollama classifier support
- OCR/vision/text safety pipeline
- Local encrypted evidence storage
- Initial installer/deployment docs
- AGPL-3.0 licensing

Known limitations:

- Alpha software
- May miss risks or false-alarm
- Setup and hardening are still evolving
- LAN TLS/mTLS is not built in by default
- Signed installers are available only when release artifacts are explicitly signed
- Screenshot/OCR evidence may include sensitive on-screen information
