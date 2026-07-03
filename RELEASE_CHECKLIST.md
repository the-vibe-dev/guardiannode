# Public Alpha Release Checklist

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
- [ ] Docker Compose config validates.
- [ ] Docker image builds.
- [ ] Installer build passes if installers are included.
- [ ] Source alpha release workflow passes without publishing installer artifacts.

## 3. Security/Privacy

- [ ] Backend is not exposed directly to the public internet.
- [ ] Admin password is set.
- [ ] Evidence encryption key is backed up if evidence recovery matters.
- [ ] LAN/TLS limitations are documented.
- [ ] No child screenshots, private messages, evidence exports, or sensitive logs
      are included in issues, docs, samples, fixtures, or release assets.

## 4. Release Artifacts

- [ ] Version tag created and signed or otherwise verified by an approved
      maintainer key.
- [ ] Changelog updated.
- [ ] Installer hashes generated if installers are included.
- [ ] Installer assets, if included, match the release tag, documented
      SHA-256 hashes, signing status, and Windows validation evidence.
- [ ] Release notes include alpha warnings.

## 5. Messaging

- [ ] Do not claim production readiness.
- [ ] Do not claim detection is certain.
- [ ] Do not claim redaction is certain.
- [ ] Do not claim signed installers unless artifacts are actually signed.
- [ ] Unsigned installer release notes include SmartScreen/Defender warning
      guidance and checksum verification steps.
- [ ] Use "alpha/developer preview".
