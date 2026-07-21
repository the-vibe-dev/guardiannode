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
- [x] Verify the downloaded final-tag installer checksums against the generated
      `SHA256SUMS` file.
- [ ] Sign Windows installers and verify uploaded signatures.
- [ ] Run current Windows 11 and Windows 10 qualification plus suspend/resume.
- [x] Capture current dashboard/demo screenshots without real family data from
      the rebuilt source candidate; repeat on the qualified Windows artifact if
      that platform renders differently.
- [x] Keep unrelated untracked WordPress/scratch files out of every Build Week
      commit and release artifact.

## Guardian Review implementation gates

- [x] Implement migration, durable job worker, provider clients, and backend
      routes; fail closed the coding-agent connection after security review.
- [x] Keep direct API mode disabled unless ZDR is confirmed and a server-side
      API key is present; keep Codex OAuth transport on a zero-tool security hold.
- [x] Implement local minimization/redaction and exact outbound preview.
- [x] Require per-review consent bound to the preview digest.
- [x] Validate every result against schema `1.1.0`; reject uncontrolled output.
- [x] Add deterministic mock mode, six dashboard scenarios, and 55 evaluation cases.
- [x] Add Guardian Review-specific local feedback and evaluation reporting.
- [x] Complete backend privacy, auth, retry, timeout, idempotency, prompt
      injection boundary, and audit-data tests.
- [x] Add alert-page preview, consent, cancel, result, history, deletion, and
      accessibility-oriented interaction tests.
- [x] Add Guardian Review-specific feedback and expand the frozen judge
      scenario set.

## Final submission gates

- [x] Replace preliminary Devpost language with demonstrated results only.
- [x] Record final demo steps, supported platform, model, schema, and prompt
      versions.
- [x] Re-run repository, dependency, secret, documentation, and Windows release
      automation gates on the exact tagged release commit.
- [x] Run Windows 11 all-in-one and separate child/server qualification with
      exact `0.1.0-alpha.3` artifacts. Clean uninstall/reinstall and Windows 10
      remain disclosed follow-up gates.
- [x] Verify public repository/evidence links and both generated installer
      checksums. Verify the draft release link while logged out after promotion.
- [x] Review the submission for child-safety claims and emergency limitations.
- [x] Add a timed Codex-computer video package: script, voiceover, captions,
      shot manifest, operating prompt, disposable server, and watch-through.
- [x] Add a final claim-to-evidence review and private-notes template.
- [ ] Confirm the external Build Week credit-request form was submitted; do not
      store credentials or form responses in the repository.
- [x] Produce and checksum the functional 2:48 video with live synthetic
      client/server alert, live GPT-5.6 review, Coral narration, and captions.
- [ ] Upload the video to YouTube as Public and verify it while logged out.
- [ ] Run `/feedback` in the same Codex thread and store its Session ID in the
      private submission notes, never in public repository content.
- [ ] Submit Devpost, save the confirmation privately, and record the exact
      submitted tag/commit and video URL.
