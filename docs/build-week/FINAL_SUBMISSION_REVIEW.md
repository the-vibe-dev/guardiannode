# Final Submission Review

This is the freeze record for GuardianNode `0.1.0-alpha.2`. It separates
repository-verifiable evidence from the real-node and account actions that the
maintainer will complete against the exact tagged commit.

## Submission identity

| Field | Frozen value |
|---|---|
| Project | GuardianNode — Guardian Review |
| Track | Apps for Your Life |
| Version | `0.1.0-alpha.2` |
| Baseline tag | `pre-build-week-2026` |
| Baseline commit | `36b2a547056d40eff32f00aa59b7820f7d3e98d5` |
| Final Build Week tag | `guardian-node-build-week-2026-final` |
| Frozen release commit | `62590db1911cb84cf01b27de76ab26f238d003d7` |
| Runtime model default | `gpt-5.6` via OpenAI Responses API |
| Schema / prompt / redaction | `1.1.0` / `guardian-review-v2` / `guardian-review-redaction-v3` |
| Repository | `https://github.com/the-vibe-dev/guardiannode` |
| License | AGPL-3.0 |

The final tag resolves to the frozen release commit above. A later
documentation-only evidence merge may advance `main`; record the immutable tag
commit as the judged binary/source release unless tomorrow's qualification
requires a reviewed replacement release.

## Release artifact evidence

The [final release workflow](https://github.com/the-vibe-dev/guardiannode/actions/runs/29697304602)
completed successfully and created a draft prerelease. The downloaded
`SHA256SUMS` file verified both installers:

| Artifact | SHA-256 |
|---|---|
| `GuardianNodeChildSetup-0.1.0-alpha.2.exe` | `a487937abc44e80036a5eb0d823868e7fdb3d06c60efe8724a873758c008251d` |
| `GuardianNodeServerSetup-0.1.0-alpha.2.exe` | `b289432a8a97c7ad93dab13e09984f83925b12c6b8716a977dd40c7ab3a8fd15` |

The release stays draft until real-node qualification. The installers are
unsigned alpha artifacts and must not be described as production-qualified.

## Claim-to-evidence review

| Submission claim | Repository evidence | Decision |
|---|---|---|
| GuardianNode existed before Build Week | `BASELINE.md` and baseline tag | Supported |
| Portions of the prior visual web UI were Claude-assisted | Owner disclosure, explicitly not fully Git-verifiable | Supported as attributed disclosure |
| Guardian Review is the Build Week extension built with Codex/GPT-5.6 | Baseline comparison, changelog, collaboration log | Supported |
| Existing incidents can produce a structured local assessment | Backend/UI tests and synthetic harness | Supported |
| Parent previews and controls outbound context | Exact preview/consent implementation and tests | Supported |
| Live mode uses Responses API, `gpt-5.6`, strict output, no tools, `store:false` | Provider implementation and tests | Supported |
| Mock judge flow uses no real family data or API key | Six manufactured fixtures and disposable demo helper | Supported |
| Model output determines truth or punishment | No such capability | Must not claim |
| GuardianNode diagnoses conditions or replaces emergency help | No such capability | Must not claim |
| `store:false` guarantees zero retention | Not supported by OpenAI contract | Must not claim |
| All GuardianNode functionality was built during Build Week | Contradicted by baseline | Must not claim |
| Production/clinical/universal model accuracy | Not evaluated | Must not claim |

## Locally verifiable freeze gates

- Complete backend/E2E, agent, dashboard, and release/control test suites.
- Guardian Review authorization, privacy, malformed output, timeout, retry,
  duplicate, cancellation, audit, and persistence tests.
- Mock golden-path browser capture against a disposable backend.
- Backend and agent lint; backend type check; dashboard type/build.
- Version, feature matrix, notices/licenses, repository controls, and strict
  documentation checks.
- Backend, agent, and production dashboard dependency audits.
- Secret scan of the exact candidate and public-history review.
- Local Markdown links, README disclosure, Devpost sections, video duration, and
  required production assets via `scripts/check_build_week_submission.py`.

Exact results belong in `DAILY_2026-07-21.md` after the final run.

## Tomorrow: real-node and account gates

Complete these against the exact tagged commit/artifacts and attach private
evidence where appropriate:

- [x] Verify artifact SHA-256 against the generated checksum file.
- [x] Install the exact `0.1.0-alpha.3` artifacts on Windows 11 all-in-one and
      child/server qualification nodes.
- [x] Complete setup, parent account, backend/agent startup, enrollment, reboot,
      mock flow, real synthetic client/server alert, and live GPT-5.6 review.
- [x] Produce the functional 2:48 video using the supplied production kit.
- [x] Verify duration, streams, key frames, claims, and absence of visible
      secrets/personal data. Final human audio listening remains an upload gate.
- [ ] Upload to YouTube as Public and verify while signed out.
- [ ] Verify repository and final tag while signed out.
- [ ] In this Codex thread, run `/feedback` and copy the returned Session ID to
      private submission notes only.
- [ ] Select **Apps for Your Life**, paste the finalized copy, compare every
      claim once more, and submit well before the deadline.
- [ ] Save the Devpost confirmation and sanitized screenshot outside the judged
      repository.
- [ ] Record the submitted commit, tag, repository URL, and video URL privately.

## Freeze rule

After submission, do not move the final tag or materially alter the judged
version. If real-node testing finds a blocking defect before submission, make a
reviewed fix, rerun proportionate checks, create a new version/tag, and update
the private submitted-commit record. Never rewrite the baseline tag.
