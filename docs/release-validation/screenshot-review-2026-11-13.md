# Screenshot review integration — 2026-11-13

The review.3 source package was verified against its 654-entry SHA-256 manifest
and integrated onto the current Git tree. The supplied PDF and ZIP remain in a
local gitignored review folder. This repository retains the newer workflow
pins, Python 3.12 base image, and dashboard dependency lock from the preceding
branch reconciliation. The dashboard production assets are rebuilt from this
repository's source and lockfile.

The current product path is permitted screenshot capture, encrypted buffering,
server acceptance, OCR/rules/AI assessment, retained evidence, and parent
review. New app or website restrictions and child exception approvals are
retired. The endpoint keeps release-only recovery for previously recorded
restrictions. Screenshot monitoring pause and privacy consent remain active.

The review also improves admission-aware deduplication, per-device processing
status, malformed-model response handling, modality-aware diagnostics,
retained-image reveal and deletion, and source-aware alert grouping.

Validation in this integration checkout: 556 backend/API and repository E2E
tests, 176 Windows-agent unit tests, 71 repository contract tests, 88 dashboard
component tests, and 16 desktop/mobile browser tests passed. Backend and agent
Ruff, backend Mypy, and dashboard TypeScript checks passed. The generated API
client matched the current 93-path OpenAPI schema, the rules-only synthetic
benchmark passed its gate, and the rebuilt 81 dashboard assets matched the
review package. These checks use synthetic inputs; they do not measure real
model accuracy.

This edition needs native Windows installer and broker qualification, an actual
Docker deployment check, representative OCR/model accuracy measurements, and
upgrade/rollback testing before promotion beyond an engineering preview. No
installed lab machine was changed by this source integration.
