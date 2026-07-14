# Codex Collaboration Record

## Build Week day one

Codex was used to inspect repository history and refs, determine the cutoff from
commit timestamps, inventory tracked/untracked/release artifacts, run the
practical test suite, trace the current incident pipeline, audit public-release
risks, and draft the Guardian Review architecture and strict schema.

No child screenshot, family message, credential, evidence export, or production
database was submitted to an external model as part of this work. The baseline
tests use repository fixtures and synthetic scenarios. No Guardian Review
runtime call was made.

## Evidence and review discipline

- Baseline claims are tied to Git hashes, timestamps, tracked files, tests, or
  existing release evidence.
- Planned functionality is labeled planned and is not presented as shipped.
- Secret-scanner findings were reviewed in redacted form; no secret value is
  reproduced here.
- Existing untracked files were deliberately excluded from every repository
  operation.
- The repository owner remains responsible for reviewing the final diff,
  product claims, privacy decisions, and release submission.

## Prior-work attribution

The owner describes the pre-Build Week dashboard and visual UI as
Claude-assisted. The owner describes the existing Windows agent, backend,
security controls, installers, and platform hardening as Codex-built. Git does
not consistently identify the assistant responsible for each historical line,
so this is an owner-supplied disclosure, not an independently proven Git fact.

## Runtime role planned for GPT-5.6

GPT-5.6 is planned only for the opt-in Guardian Review second-opinion service.
Local detection remains the event source. Before each cloud request, the local
backend will minimize/redact an allowlisted DTO, show the exact outbound JSON to
the parent, bind explicit consent to its digest, and require verified Zero Data
Retention. The model response will be accepted only through the versioned strict
schema. It will not directly change enforcement or contact a child.
