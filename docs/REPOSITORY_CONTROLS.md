# Repository Controls Maintainer Checklist

This file records repository settings that cannot be fully enforced from source
code. Complete these settings before cutting a public source tag, and re-check
them before installer or stable releases.

## Branch Protection For `main`

- [ ] Require pull requests before merging.
- [ ] Require at least one approving review.
- [ ] Require review from CODEOWNERS.
- [ ] Dismiss stale approvals when new commits are pushed.
- [ ] Require conversation resolution before merge.
- [ ] Require linear history or squash merges according to maintainer policy.
- [ ] Block force pushes.
- [ ] Block branch deletion.
- [ ] Restrict who can bypass branch protection.

Required status checks for source changes:

- [ ] `tests / actionlint`
- [ ] `tests / backend`
- [ ] `tests / agent`
- [ ] `tests / agent-windows-bundle`
- [ ] `tests / dashboard`
- [ ] `tests / release-scripts`
- [ ] `deploy-docs`

## Protected Tags And Releases

- [ ] Protect `v*` tags.
- [ ] Restrict tag creation/deletion to release maintainers.
- [ ] Require a signed or otherwise verified tag for public releases.
- [ ] Confirm `v0.1.0-alpha.1` and all ordinary `v*` tags use the source-only
      workflow, not the installer workflow.
- [ ] Confirm source releases contain no `.exe`, `.msi`, or unsigned installer
      attachments.
- [ ] Keep installer qualification tags on the dedicated
      `v*-installer-test*` path until the Windows gate passes.

## Security Features

- [ ] Enable GitHub secret scanning.
- [ ] Enable push protection.
- [ ] Enable private vulnerability reporting.
- [ ] Enable Dependabot alerts.
- [ ] Enable Dependabot security updates where available.
- [ ] Keep `.github/dependabot.yml` active for GitHub Actions, backend Python,
      agent Python, dashboard npm, and Docker dependencies.

## Code Ownership

- [ ] Verify `.github/CODEOWNERS` resolves to real maintainers or teams.
- [ ] Require CODEOWNERS review for workflows, security/privacy docs, licenses,
      installers, encryption, credentials, device pairing, queueing, evidence,
      exports, and release scripts.
- [ ] Revisit CODEOWNERS whenever new broker/service, database migration,
      release signing, or backup/restore paths are added.

## Release Approval Environments

- [ ] Installer release workflows require a protected GitHub Environment.
- [ ] The environment requires explicit maintainer approval.
- [ ] The environment has no long-lived plaintext signing secrets.
- [ ] Signing credentials are hardware-backed or cloud-KMS backed where
      possible.

## Verification Before Source Alpha

- [ ] Live source CI is green on the exact release commit.
- [ ] A fresh clone README smoke test has been performed.
- [ ] The release tag matches `VERSION`.
- [ ] The release tag is signed or verified by an approved maintainer key.
- [ ] Release notes mark the release as source-only alpha/developer preview.
- [ ] Windows installer artifacts remain unavailable to ordinary users.
