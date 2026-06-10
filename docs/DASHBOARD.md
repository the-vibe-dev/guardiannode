# Dashboard

React + Vite + Tailwind. Served by the backend at `/` in production; runs separately in dev.

## Development

```bash
cd dashboard
npm install
npm run dev
```

Dev server on `http://localhost:5173`, proxies `/api/*` to backend on `:8787`.

## Production build

```bash
npm run build
```

Output to `dist/`, which the backend serves as static files.

## Pages

- `/setup` — first-run wizard (admin account, encryption key, model pull)
- `/login` — sign-in
- `/` — overview dashboard
- `/devices` — manage devices, pairing codes
- `/profiles` — child profiles
- `/risks` — risk feed (filterable)
- `/risks/:id` — alert detail
- `/policies` — per-profile policy editor
- `/models` — Ollama model status + test
- `/settings` — notifications, retention, network, migration

## API client

`src/api.ts` — typed wrapper around backend endpoints. Uses fetch with auth header set from localStorage.

## Auth

Argon2id password verification on `/api/auth/login` → backend issues a session cookie (HttpOnly, SameSite=Strict). All API calls use cookie-based auth except agent token endpoints.

## Styling

Tailwind utility classes. Custom theme in `tailwind.config.js`. Dark mode toggle in settings.
