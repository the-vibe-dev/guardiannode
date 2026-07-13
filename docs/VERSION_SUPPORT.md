# Version Support Policy

GuardianNode qualifies exact release inputs rather than floating "latest"
versions. Dependency and image updates must pass the same gates as the versions
they replace.

## Closed-beta baseline

| Component | Supported baseline | Policy |
|---|---|---|
| Windows | Windows 11 current stable, x64 | The golden gate records the tested build number. Windows 10 is not promoted by this plan. |
| Python | CPython 3.12 | CI, Docker, Windows bundles, and developer instructions must agree. |
| Node.js | Node.js 24 | Dashboard builds use the committed npm lock and a pinned npm release. |
| Docker Engine | A maintained Engine release with BuildKit | The canary records `docker version`; release images remain digest-pinned. |
| Docker Compose | v2.24 or newer | Required for the supported Compose syntax; the exact canary version is recorded. |
| Tesseract | 5.5, `eng` language data | `eng` is the only initially qualified pack. Additional packs require fixtures and a canary. |
| Ollama | 0.13.5 | Container images are digest-pinned; configured model tags must exist before readiness passes. |
| SQLite | The version bundled with supported CPython 3.12 | Startup records the runtime version and validates the Alembic revision. |
| Inno Setup | 6.7.1 | Installer URL and SHA-256 are pinned in release automation. |
| WinSW | 2.12.0 | Binary URL and SHA-256 are pinned in release automation. |

## Update policy

- Patch and minor updates are accepted only after locks/digests are refreshed,
  audits pass, and all affected platform gates are green.
- Runtime major-version updates require an explicit qualification change; upper
  bounds are not widened in anticipation of an untested major release.
- Release notes record exact Python, Node/npm, Docker/Compose, Tesseract,
  Ollama/model, SQLite, PyInstaller, Inno Setup, and WinSW versions.
- Security exceptions require an owner, rationale, compensating control, and
  expiry. An expired exception blocks release.
