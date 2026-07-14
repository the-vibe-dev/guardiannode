# Submission Checklist

## Completed for the baseline

- [x] Verified the last pre-cutoff commit from Git timestamps and origin state.
- [x] Created `pre-build-week-2026` at the baseline commit.
- [x] Created `build-week/guardian-review` from that commit.
- [x] Preserved unrelated untracked and ignored work.
- [x] Recorded modules, prior features, tests, release artifacts, UI evidence,
      assisted-work disclosure, and known defects.
- [x] Ran the practical baseline suite before Guardian Review implementation.
- [x] Audited license, notices, dependencies, links, configuration, secrets,
      personal data, tracked artifacts, and file sizes.
- [x] Defined the golden path, privacy model, API contract, strict schema, mock
      mode, evaluation approach, and audit model.
- [x] Added existing-project and Build Week disclosure to the README.

## Public repository decision

The GitHub repository was already public before this audit. After sanitizing
current release-validation infrastructure labels, it is reasonable to keep the
repository public: no verified credential, API key, real child/family dataset,
or oversized tracked build artifact was found. Repository visibility is not
changed by this work.

Remaining public/submission caveats:

- [ ] Historical commits retain prior lab host/address metadata. Removing it
      requires a separately approved coordinated history rewrite; it is not a
      credential and current documentation is sanitized.
- [ ] Sign Windows installers and verify uploaded signatures/checksums.
- [ ] Run current Windows 11 and Windows 10 qualification plus suspend/resume.
- [ ] Capture current dashboard/demo screenshots without real family data.
- [ ] Ensure unrelated untracked WordPress/scratch files are never staged.

## Guardian Review implementation gates

- [ ] Implement migrations, durable job worker, service client, routes, and UI.
- [ ] Keep live mode disabled unless ZDR is contractually/configurationally
      confirmed and an API key is present.
- [ ] Implement local minimization/redaction and exact outbound preview.
- [ ] Require per-review consent bound to the preview digest.
- [ ] Validate every result against schema `1.0.0`; reject uncontrolled output.
- [ ] Add deterministic mock mode and synthetic judge scenarios.
- [ ] Add Guardian Review-specific feedback and evaluation reporting.
- [ ] Complete privacy, auth, retry, timeout, idempotency, injection, audit, and
      accessibility tests from the evaluation plan.

## Final submission gates

- [ ] Replace preliminary Devpost language with demonstrated results only.
- [ ] Record final demo steps, supported platform, model, schema, and prompt
      versions.
- [ ] Re-run repository, dependency, secret, documentation, Docker, and Windows
      release gates on the exact submission commit.
- [ ] Verify every external link and every release artifact checksum.
- [ ] Review the submission for child-safety claims and emergency limitations.
