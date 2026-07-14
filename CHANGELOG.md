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
