# Reproducible Builds & Release Verification

GuardianNode is open source and alpha builds may ship unsigned installers (see
[SIGNING_PLAN.md](https://github.com/the-vibe-dev/guardiannode/blob/main/installer/shared/SIGNING_PLAN.md)). Until code signing lands,
verifiable checksums are how a parent confirms a download is the artifact we
published.

## What ships with every release

- The installer `.exe` files (child device + server).
- A `SHA256SUMS` file listing the SHA-256 of each `.exe`.

`SHA256SUMS` is generated automatically by `installer/build/build_all.sh` (step 8)
and printed at the end of the build.

## How a parent verifies a download

Windows (PowerShell):

```powershell
Get-FileHash .\GuardianNodeChildSetup-0.1.0-alpha.1.exe -Algorithm SHA256
```

Compare the printed hash against the matching line in `SHA256SUMS` on the
[Releases page]. Linux/macOS:

```bash
sha256sum -c SHA256SUMS
```

If the hashes do not match, do not run the installer — re-download from the
official releases page and report a mismatch via [SECURITY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md).

## Build inputs that affect reproducibility

The Windows installers are built under Wine + PyInstaller + Inno Setup via
`installer/build/build_all.sh`. Bit-for-bit reproducibility is **not yet
claimed**; the following inputs must be pinned to approach it:

| Input | Where pinned |
|---|---|
| Python version + deps | Python 3.12 and committed `backend/uv.lock` / `agent-windows/uv.lock` |
| Python resolver | `uv==0.11.28` in CI |
| Node version + deps | Node 24, npm 11.6.2, and committed `dashboard/package-lock.json` |
| PyInstaller version | `6.16.0` in CI |
| Inno Setup version | `installer/build/innosetup-6.7.1.exe` |
| WinSW version | `installer/build/WinSW-x64.exe` |

CI installs Python environments with `uv sync --frozen` and dashboard packages
with `npm ci`. Docker's Python and Node images are pinned by manifest digest.
Ruff, mypy, tests, dependency audits, dashboard tests/build, migrations, and the
clean Docker canary are blocking checks.

Known sources of nondeterminism that remain documented rather than hidden:

- PyInstaller embeds timestamps/paths; set `SOURCE_DATE_EPOCH` and a fixed build
  path in CI.
- Inno Setup compression metadata can vary by toolchain version.
- Generated icons are produced at build time — commit the generated `.ico` or pin
  the generator.

Release workflows publish SHA-256 checksums and a release manifest. Bit-for-bit
installer equivalence is not claimed until PyInstaller and Inno timestamp/path
differences are normalized and independently compared.
