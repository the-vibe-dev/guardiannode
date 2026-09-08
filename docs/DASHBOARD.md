# Dashboard

React + Vite + Tailwind. Served by the backend at `/` in production; runs separately in dev.

## Development

```bash
cd dashboard
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api/*` to a
loopback development backend. Never use the HTTP development path for family data.

## Production build

```bash
npm run build
```

Output to `dist/`, which the backend serves as static files.

## Pages

- `/setup` — first-run parent account and recovery phrase
- `/login` — sign-in
- `/` — alert-first family overview and guided setup progress
- `/devices` — manage devices and secure `.gnpair` trust bundles
- `/profiles` — child profiles
- `/risks` — risk feed (filterable)
- `/alerts/:id` — alert detail, feedback, and parent-confirmed device actions
- `/requests` — parent review of child time/site/app requests
- `/privacy` — explicit privacy choices, consent, and withdrawal
- `/models` — Ollama model status + test
- `/settings` — notifications, retention, complete recovery backups, and local encrypted exports

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
