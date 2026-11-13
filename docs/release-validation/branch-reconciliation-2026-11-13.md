# Remote branch reconciliation — 2026-11-13

The November review branch was fast-forwarded to `main` at `7213249` before this
reconciliation. All remaining remote branch tips were compared with that main
tree. The reconciled result records every tip in Git ancestry; older dependency
proposals were combined against the current lockfile instead of replaying their
old lockfiles over the reviewed application.

The local `safety/beta-hardening-pre-rebase-20260908` snapshot predates the
current `6801d48` implementation of the same security work. Its history was
recorded as merged without replaying its older tree over the later fixes.

| Remote branch | Result |
| --- | --- |
| `review/independent-hardening-20261031` | Already included by the November review merge. |
| `review/november-upgrades-20261113` | Already identical to main before reconciliation. |
| `dependabot/github_actions/actions/deploy-pages-5.0.1` | Merged; pinned action updated to 5.0.1. |
| `dependabot/github_actions/docker/build-push-action-7.4.0` | Merged; pinned action updated to 7.4.0. |
| `dependabot/github_actions/docker/login-action-4.6.0` | Merged; pinned action updated to 4.6.0. |
| `dependabot/github_actions/docker/setup-buildx-action-4.4.1` | Merged; pinned action updated to 4.4.1. |
| `dependabot/github_actions/softprops/action-gh-release-3.0.3` | Merged; pinned action updated in both workflows. |
| `dependabot/npm_and_yarn/dashboard/fontsource/sora-5.3.0` | Recorded as merged; Sora 5.3.0 applied to the current package and lockfile. |
| `dependabot/npm_and_yarn/dashboard/lucide-react-1.43.0` | Recorded as merged; Lucide 1.43.0 applied. |
| `dependabot/npm_and_yarn/dashboard/multi-de36fa8f59` | Recorded as merged; React, React DOM, and their types moved together to 19.3.0 to satisfy peer dependencies. |
| `dependabot/npm_and_yarn/dashboard/react-router-dom-7.18.3` | Recorded as merged; React Router 7.18.3 applied. |
| `dependabot/npm_and_yarn/dashboard/vite-8.2.2` | Recorded as merged; existing Vite 8.3.8 retained. |
| `dependabot/pip/agent-windows/pillow-gte-12.2-and-lt-14.0` | Recorded as merged; existing Pillow 13 floor is stricter. |
| `dependabot/pip/backend/pillow-gte-12.2-and-lt-14.0` | Recorded as merged; existing Pillow 13 floor is stricter. |
| `dependabot/pip/agent-windows/python-ulid-gte-2.2-and-lt-5.0` | Recorded as merged; existing `<4.0` major-version bound retained. |
| `dependabot/pip/backend/python-ulid-gte-2.2-and-lt-5.0` | Recorded as merged; existing `<4.0` major-version bound retained. |
| `dependabot/docker/installer/server-linux/python-3.15.0-slim-bookworm` | Recorded as merged; runtime image stays on Python 3.12.13 until a 3.15 build and migration qualification succeeds. |

Dependabot is configured to keep Python on its qualified minor series while
allowing patch releases, and to defer `python-ulid` major-version proposals.
Those gates can be removed after the corresponding compatibility tests.

The dashboard production assets in `backend/app/static` were rebuilt from the
consolidated package lock. Validation: frozen npm install, TypeScript check,
76 component tests, 16 desktop/mobile Playwright tests, production build,
workflow YAML parsing, and an exact `dashboard/dist` to `backend/app/static`
comparison. These checks do not qualify a native Windows installer or change
the installed test machines.

## Dependabot follow-up generated during cleanup

Dependabot created a further eight branches while reconciling the first batch.
Their tips were also recorded as merged, and the following changes were
applied against the current tree:

| Branch update | Applied result |
| --- | --- |
| Docker `python:3.12.16-slim-bookworm` | Updated the backend image within the qualified 3.12 series. |
| `actions/setup-node` 7.1.0, `actions/setup-python` 7.1.0, `actions/upload-artifact` 7.0.2, `softprops/action-gh-release` 3.0.4 | Updated the pinned workflow revisions wherever used. |
| `autoprefixer` 10.6.2, `jsdom` 31.0.0, `@testing-library/react` 16.3.3 | Updated dashboard development dependencies and lockfile together. |

The follow-up passed frozen npm install, TypeScript check, 76 component tests,
16 desktop/mobile Playwright tests, and a production build. Production assets
matched the already packaged build byte for byte. Workflow YAML parsed. The
local Docker daemon was unavailable, so the new base image needs the GitHub CI
Docker build before it is treated as qualified.
