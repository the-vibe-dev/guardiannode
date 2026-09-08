# Closed Beta Release Checklist

## 1. Repo Hygiene

- [ ] License is AGPL-3.0.
- [ ] CODEOWNERS exists and resolves to real maintainers or teams.
- [ ] Main branch protection, protected tags, secret scanning, push protection,
      Dependabot alerts, and private vulnerability reporting are configured
      according to `docs/REPOSITORY_CONTROLS.md`.
- [ ] No placeholder emails or fake contact domains remain.
- [ ] No obvious broken documentation links or missing referenced files.
- [ ] README says alpha/developer preview.
- [ ] Known limitations are current.

## 2. Build/Test

- [ ] Backend tests pass.
- [ ] Agent tests pass.
- [ ] Dashboard typecheck/build/tests pass.
- [ ] Dashboard Chromium journeys pass at desktop and mobile viewports with no
      serious/critical axe violations, console errors, or page errors.
- [ ] Docker Compose config validates.
- [ ] Docker image builds.
- [ ] Installer build passes if installers are included.
- [ ] The exact Windows artifacts pass clean install, reboot, user switching,
      sleep/wake, RDP, upgrade, repair, uninstall, and reinstall on a supported
      standard-user/admin matrix.
- [ ] Capture-to-alert synthetic canary succeeds after install and reboot.
- [ ] Source alpha release workflow passes without publishing installer artifacts.

## 3. Security/Privacy

- [ ] Backend is not exposed directly to the public internet.
- [ ] Admin password is set.
- [ ] Evidence encryption key is backed up if evidence recovery matters.
- [ ] Family CA generation, browser trust, `.gnpair` expiry/fingerprint, wrong-CA
      rejection, and non-loopback HTTP rejection are tested.
- [ ] Broker pipe capability, concurrency/deadline bounds, credential ACLs, and
      absence of a legacy agent scheduled task are qualified on Windows.
- [ ] Backup/restore and deletion drills have current evidence.
- [ ] Incident response contacts and vendor inventory are reviewed.
- [ ] Consent notice, withdrawal paths, child-facing notice, and retention
      choices match the exact build.
- [ ] No child screenshots, private messages, evidence exports, or sensitive logs
      are included in issues, docs, samples, fixtures, or release assets.

## 4. Release Artifacts

- [ ] Version tag created and signed or otherwise verified by an approved
      maintainer key.
- [ ] Changelog updated.
- [ ] Installer hashes generated if installers are included.
- [ ] Installer assets, if included, match the release tag, documented
      SHA-256 hashes, signing status, and Windows validation evidence.
- [ ] Privileged dependency downloads pass pinned SHA-256 and signer checks.
- [ ] Installer and executable signatures are verified, or the build remains a
      supervised unsigned evaluation and is not promoted to ordinary families.
- [ ] SBOM/vendor notice inventory matches locked dependencies and bundled code.
- [ ] Release notes include alpha warnings.

## 5. Messaging

- [ ] Do not claim production readiness.
- [ ] Do not claim detection is certain.
- [ ] Do not claim redaction is certain.
- [ ] Do not claim signed installers unless artifacts are actually signed.
- [ ] Unsigned installer release notes include SmartScreen/Defender warning
      guidance and checksum verification steps.
- [ ] Clearly distinguish source-tested, platform-qualified, field-validated,
      and externally reviewed claims.
- [ ] Use "closed-beta candidate" until every required gate for the same commit
      is evidenced.
