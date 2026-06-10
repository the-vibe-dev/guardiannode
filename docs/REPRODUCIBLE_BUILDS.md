# Reproducible Builds & Release Verification

GuardianNode is open source and ships unsigned beta installers (see
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
Get-FileHash .\GuardianNodeChildSetup.exe -Algorithm SHA256
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
guaranteed**; the following inputs must be pinned to approach it:

| Input | Where pinned |
|---|---|
| Python version + deps | `backend/requirements*.txt`, `agent-windows` venv |
| Node version + deps | `dashboard/package.json` (committed lockfile) |
| PyInstaller version | build environment (document in release notes) |
| Inno Setup version | `installer/build/innosetup-6.7.1.exe` |
| WinSW version | `installer/build/WinSW-x64.exe` |

Known sources of nondeterminism still to address before claiming reproducible
builds:

- PyInstaller embeds timestamps/paths; set `SOURCE_DATE_EPOCH` and a fixed build
  path in CI.
- Inno Setup compression metadata can vary by toolchain version.
- Generated icons are produced at build time — commit the generated `.ico` or pin
  the generator.

## Roadmap

1. Move builds into public CI (GitHub Actions) so the build environment is
   transparent and logs are public — also a prerequisite for SignPath OSS signing.
2. Pin all toolchain versions and set `SOURCE_DATE_EPOCH`.
3. Publish CI build logs alongside each release so a third party can reproduce and
   diff `SHA256SUMS`.
