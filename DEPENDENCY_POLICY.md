# Dependency Policy

## Allowed licenses (no review needed)

- MIT
- Apache-2.0
- BSD-2-Clause
- BSD-3-Clause
- ISC
- 0BSD / Unlicense
- HPND
- PSF-2.0 (Python Software Foundation)
- Zlib

## Requires review

- MPL-2.0 — copyleft applies only to the licensed file, generally fine
- LGPL-2.1 / LGPL-3.0 — must be used dynamically as an unmodified library, not statically linked or forked

## Disallowed as hard dependency

- GPL-2.0, GPL-3.0
- AGPL-3.0 (especially: AGPL flips even network use into a distribution event)
- Server-Side Public License (SSPL)
- Anything labeled "non-commercial only"
- Anything with unclear/missing license

Disallowed licenses may still be **optional plugins** loaded via dynamic import or a separate process — but never `pip install`/`npm install` defaults.

## Disallowed dependency *categories*

- **Cloud API SDKs as defaults** — anything calling out to a third-party SaaS at runtime by default. Notifications via SMTP and webhook are allowed because the parent configures the endpoint.
- **Telemetry / analytics SDKs** — `sentry`, `posthog`, etc. We do not ship error reporting to outside servers.
- **Closed-source binaries** — except for vendored installers that the parent explicitly approves (e.g. the Ollama installer itself, which is open-source but distributed as a binary).
- **Model weights** — never in the repo, never in pip/npm packages we publish.

## How to add a dependency

1. Check its license against the lists above.
2. Check it has been maintained in the last 12 months.
3. Check it has no known critical CVEs (`pip-audit` / `npm audit`).
4. Add it to the relevant `pyproject.toml` / `package.json` with a *minimum* and *exclusive maximum* version range (`>=1.2.0,<2.0.0`).
5. If license is in the "Requires review" tier, get a maintainer ack on the PR.
6. Update [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
7. CI runs `scripts/check_licenses.py` which fails if anything violates the policy.

## Vendored binaries

We vendor (download at build time, never to the repo) these binaries:
- **WinSW** (`winsw.exe`) — MIT — Windows service wrapper. Verified by SHA-256 hash at install time.
- **Ollama installer** (`OllamaSetup.exe` on Windows) — MIT — downloaded from `ollama.com`, verified by published SHA-256.
- **Inno Setup** (build-time only, for the installer build pipeline) — Modified BSD — downloaded from `jrsoftware.org`.

Hashes for these binaries are pinned in `installer/build/binary_hashes.json`.

## Periodic review

- **Quarterly**: maintainers review for dependencies that have stopped being maintained
- **On every PR**: automated CI license check
- **On every release**: full `pip-audit` and `npm audit` run
