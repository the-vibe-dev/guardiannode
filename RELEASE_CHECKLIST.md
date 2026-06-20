# Public Alpha Release Checklist

## 1. Repo Hygiene

- [ ] License is AGPL-3.0.
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

## 3. Security/Privacy

- [ ] Backend is not exposed directly to the public internet.
- [ ] Admin password is set.
- [ ] Evidence encryption key is backed up if evidence recovery matters.
- [ ] LAN/TLS limitations are documented.
- [ ] No child screenshots, private messages, evidence exports, or sensitive logs
      are included in issues, docs, samples, fixtures, or release assets.

## 4. Release Artifacts

- [ ] Version tag created.
- [ ] Changelog updated.
- [ ] Installer hashes generated if installers are included.
- [ ] Release notes include alpha warnings.

## 5. Messaging

- [ ] Do not claim production readiness.
- [ ] Do not claim detection is certain.
- [ ] Do not claim redaction is certain.
- [ ] Do not claim signed installers unless artifacts are actually signed.
- [ ] Use "alpha/developer preview".
