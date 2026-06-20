# GuardianNode Architecture

## One-line summary

A local agent on each child's PC, a parent-owned backend with an LLM via Ollama,
an encrypted local evidence store, and a parent web dashboard. Nothing goes to a
GuardianNode cloud by default.

## Component map

```
                    ┌─────────────────────────────────────┐
                    │       Child's Windows PC            │
                    │                                     │
   ┌──────────┐     │                  ┌────────────┐    │
   │ Browsers │────►│                  │ GN Agent   │    │
   │ Apps     │────►│   (on-screen     │ (service)  │    │
   │ Games    │────►│    content)      └─────┬──────┘    │
   └──────────┘     │   screenshots          │ events    │
                    │  ┌─────────────────────▼────────┐  │
                    │  │     GN Tray + Watchdog       │  │
                    │  └──────────────┬───────────────┘  │
                    └─────────────────┼──────────────────┘
                                      │ HTTP on loopback/LAN by default
                                      │ (use VPN/TLS for stronger transport)
                    ┌─────────────────▼──────────────────┐
                    │     Backend (Win or Linux)         │
                    │  ┌──────────────────────────────┐  │
                    │  │ FastAPI ingest + API         │  │
                    │  ├──────────────────────────────┤  │
                    │  │ Redaction → Rules → LLM      │  │
                    │  ├──────────────────────────────┤  │
                    │  │ Ollama (text + vision)       │  │
                    │  ├──────────────────────────────┤  │
                    │  │ AES-GCM encrypted store      │  │
                    │  │  (SQLite + blob dir)         │  │
                    │  ├──────────────────────────────┤  │
                    │  │ Notifications · Audit · mDNS │  │
                    │  └──────────────────────────────┘  │
                    │              ▲                     │
                    │              │ React dashboard     │
                    └──────────────┼─────────────────────┘
                                   │
                            Parent's browser
                            (LAN or localhost)
```

In all-in-one mode the entire stack runs on one PC, bound to `127.0.0.1`.

## Data flow (end-to-end)

1. **Capture.** Agent reviews visible screen content from the configured Windows
   session. Current installer defaults enable full visible-screen capture; app
   names remain important context, and narrower app-gated capture is available
   through policy/config.
2. **Transmit.** Loopback HTTP (all-in-one) or LAN HTTP/VPN/TLS (separated) to
   the backend.
3. **Optional filtering.** Some paths apply basic text filtering/redaction. This
   is best-effort hygiene, not a certainty.
4. **Rules engine.** Deterministic regex/phrase rules score the event for known patterns.
5. **LLM classification (text/vision).** OCR text, screenshots, and context go to
   local/user-configured Ollama models where enabled.
6. **Multimodal merge.** Rule score + text LLM + vision LLM → final risk level + score.
7. **Encryption + storage.** Screenshot and extracted-text blobs are AES-GCM encrypted before storage. Operational metadata such as app/window/URL context, device/profile IDs, risk summaries, categories, and audit details may remain plaintext in SQLite or pending metadata files.
8. **Alert.** If severity ≥ threshold, create an Alert row and dispatch via configured channels.
9. **Audit log.** Every evidence view, decrypt, export, and pause action gets an audit row.

## Deployment shapes

| Shape | Where things run | When to use |
|---|---|---|
| **A — All-in-one** | Everything on the child's PC | Family with one PC; quickest install |
| **B — Separated** | Agent on child PC; backend+Ollama on a separate server | Multiple PCs; gaming rig + small server; better tamper isolation |
| **C — Migrated** | Started as A, moved to B without reinstall | Family upgraded hardware |

The installer picks A vs B on page 2 of its wizard. C is a post-install action.

## Module layout (repo top level)

```
backend/             FastAPI app, services, prompts, DB models, startup schema patches
agent-windows/       Python source for the Windows agent (PyInstaller bundled at build)
dashboard/           React + Vite + Tailwind frontend
shared/              JSON schemas + Pydantic models used by backend + agent
installer/           Inno Setup, Wine build scripts, Linux install.sh, Docker Compose
docs/                Architecture + parent guides + dev guides
tests/               End-to-end test harness + safety test corpus
docker/              Docker assets for self-hosted server
.github/             CI workflows + issue templates
```

## Key design choices

- **SQLite by default** — single file and easy backup for alpha deployments.
- **Startup schema patches** — the current alpha uses SQLAlchemy `create_all()`
  plus idempotent startup patches. Formal Alembic migrations are planned before
  stable release.
- **AES-GCM via Python `cryptography`** — well-audited, available on all platforms, no SQLCipher native build pain.
- **Ollama HTTP API** — abstracts the runtime; we never link to model code directly. Lets us swap llama.cpp/vLLM/MLC underneath.
- **Argon2id for passwords** — current best practice for password hashing.
- **mDNS for server discovery** — non-technical parents never have to find an IP address. Uses `_guardiannode._tcp.local`.
- **Inno Setup for Windows** — actively maintained, free, scriptable. WiX/MSI is more "enterprise" but parents don't run MSIs.
- **WinSW for service wrapping** — better logging than NSSM, MIT licensed.
- **Screenshot + server-side OCR** — one collection path (no per-browser extension to install or maintain); the vision/text classifier reads whatever is actually on screen.
- **PyInstaller one-folder mode** — reproducible, fewer false-positive antivirus hits than one-file mode.

## What we explicitly aren't doing in v1

- Kernel-mode driver (requires EV code-signing cert)
- Mobile child-device agents — roadmap order is macOS next, then Android, then
  iOS; mobile platforms have different threat models, permission systems, and
  stores
- Email client integration deeper than reading what's on screen
- Cloud-based "family share" of alerts across deployments
- ML model training — we use pretrained Ollama models exclusively

See [`docs/ROADMAP.md`](ROADMAP.md) for the post-MVP plan.
