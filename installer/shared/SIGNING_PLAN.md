# Code Signing Plan

## Problem

Without code signing, Windows shows a SmartScreen "Windows protected your PC" warning on first run. Non-technical parents are likely to close the installer at this prompt.

## v0.1 (beta) — Document the click-through

- Ship unsigned installers.
- Bundle a clear walkthrough at `docs/PARENT_GUIDES/when-windows-says-protected-your-pc.md`.
- Provide SHA-256 hashes for every release artifact.
- Mention the project status (beta, open source, no signing yet) in the SmartScreen response page.

## v0.2 — Apply for free OSS signing

Target: [SignPath.io free tier for OSS projects](https://signpath.io/open-source-projects).

Eligibility:
- Open-source repo with a permissive license (Apache-2.0 ✅)
- Active maintainers
- Public CI for reproducible builds

What it gets us:
- Code-signed Windows binaries
- Eliminates the "Unknown publisher" wording in SmartScreen
- Still subject to "newly signed by an unknown publisher" SmartScreen *reputation* warning until enough installs build reputation

Process:
1. Apply via signpath.io application form
2. Set up CI integration on GitHub Actions
3. Code-sign all .exe artifacts in `installer/build/dist/` automatically
4. Update release notes with verification instructions

## v1.0 — Microsoft Store + EV cert (stretch)

Options to compare:
- **Microsoft Store distribution**: bypasses SmartScreen entirely. Requires a $19 individual dev account or $99 company account, plus MS Store cert/review process. Apps go through store review.
- **EV code-signing certificate**: $300–600/year. Requires identity verification. Immediate SmartScreen reputation (EV certs bypass reputation building).
- **Crowdfunded cert**: pool funds from the community to purchase an EV cert for the project.

Microsoft Store distribution may be the right answer for a parent-facing tool since (a) non-technical parents already trust the Store, (b) it eliminates the SmartScreen issue entirely, and (c) the $99/year is comparable to a single year of EV cert cost.

## What we explicitly will not do

- Pay for an "extended validation" cert with project funds without a clear funding model.
- Bypass SmartScreen via tricks (kernel-mode injection, etc.).
- Sign with a stolen or shared cert.
- Promise parents that the unsigned version is "as safe as" a signed version — that's not true.
