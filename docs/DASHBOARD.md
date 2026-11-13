# Dashboard

React + Vite + Tailwind. Served by the backend at `/` in production; runs separately in dev.

## Development

```bash
cd dashboard
npm ci
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api/*` to a
loopback development backend. Never use the HTTP development path for family data.

## Production build

```bash
npm run build
```

Output is written to `dist/`. Replace the complete contents of
`backend/app/static` with that output for a matching production bundle.

## Pages

- `/setup` — first-run parent account and recovery phrase
- `/login` — sign-in
- `/` — screenshot acceptance, per-device review status, alerts and guided setup
- `/devices` — manage devices and secure `.gnpair` trust bundles
- `/profiles` — child profiles
- `/risks` — risk feed (filterable)
- `/alerts/:id` — retained screenshot, detector reasoning, review notes, feedback, optional AI second opinion and evidence deletion
- `/privacy` — explicit privacy choices, consent, and withdrawal
- `/models` — Ollama model status + test
- `/settings` — notifications, capture queues, retention, recovery backups and local encrypted exports
- `/audit` — retained audit history with filters and pagination

## API client

`src/api.ts` is the cookie-authenticated API wrapper. Core DTOs are generated
from the backend OpenAPI document into `src/api-schema.ts`; no token is stored in
`localStorage`.

## Auth

Argon2id password verification on `/api/auth/login` produces an HttpOnly,
SameSite=Strict, Secure session cookie in normal TLS operation. Mutating browser
requests require CSRF tokens; sensitive operations also require recent password
authentication. Agent endpoints use separate device credentials.

## Styling

Tailwind utility classes with bundled Inter/Sora fonts. Navigation becomes an
accessible off-canvas menu on small screens and honors reduced-motion settings.

## Browser quality gate

```bash
npm run test:e2e
```

Playwright covers desktop/mobile home, keyboard-reachable navigation, secure
pairing instructions, the core parent pages, browser-console failures, and axe
WCAG A/AA serious/critical violations. Set `PLAYWRIGHT_CHROMIUM_PATH` to a local
Chromium binary when Playwright-managed browsers are not installed.

## Product scope

No screen-time limits, schedules, app/website blocking or exception approvals
are offered. A screenshot-monitoring pause controls capture only. Historical
restriction receipts remain available solely for recovery of older installations.

Per-device status separates server receipt from completed processing and reports
AI, rules-only, degraded and unknown states. Read timestamps and diagnostics;
no alert or an empty queue is not proof of complete or safe activity coverage.
