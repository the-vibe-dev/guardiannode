# Third-Party Notices

GuardianNode bundles or directly depends on the following third-party components. Each component retains its original license.

## Backend (Python)

| Component | License | Project |
|---|---|---|
| FastAPI | MIT | https://github.com/tiangolo/fastapi |
| Starlette | BSD-3 | https://github.com/encode/starlette |
| Uvicorn | BSD-3 | https://github.com/encode/uvicorn |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| SQLAlchemy | MIT | https://www.sqlalchemy.org/ |
| Alembic | MIT | https://alembic.sqlalchemy.org/ |
| cryptography | Apache-2.0 / BSD-3 | https://github.com/pyca/cryptography |
| argon2-cffi | MIT | https://github.com/hynek/argon2-cffi |
| httpx | BSD-3 | https://github.com/encode/httpx |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| python-jose | MIT | https://github.com/mpdavis/python-jose |
| zeroconf | LGPL-2.1 | https://github.com/python-zeroconf/python-zeroconf |
| qrcode | BSD-3 | https://github.com/lincolnloop/python-qrcode |
| Pillow | HPND | https://python-pillow.org/ |
| pyyaml | MIT | https://github.com/yaml/pyyaml |

Note on `zeroconf` (LGPL-2.1): We use it as an unmodified Python package via
PyPI. Users can replace it with an alternative mDNS implementation if their
compliance requirements demand it.

## Agent (Windows)

| Component | License | Project |
|---|---|---|
| pywin32 | PSF-2.0 | https://github.com/mhammond/pywin32 |
| psutil | BSD-3 | https://github.com/giampaolo/psutil |
| mss | MIT | https://github.com/BoboTiG/python-mss |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| PaddleOCR (optional) | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| pytesseract (optional) | Apache-2.0 | https://github.com/madmaze/pytesseract |
| opencv-python | Apache-2.0 | https://github.com/opencv/opencv-python |

Note on `pystray` (LGPL-3.0): Used unmodified. Same caveat as zeroconf above.

## Dashboard (Node)

| Component | License | Project |
|---|---|---|
| React | MIT | https://github.com/facebook/react |
| Vite | MIT | https://github.com/vitejs/vite |
| Tailwind CSS | MIT | https://github.com/tailwindlabs/tailwindcss |
| React Router | MIT | https://github.com/remix-run/react-router |
| TanStack Query | MIT | https://github.com/TanStack/query |
| Zod | MIT | https://github.com/colinhacks/zod |

## Installer & Service Wrappers

| Component | License | Project |
|---|---|---|
| Inno Setup | Modified BSD | https://jrsoftware.org/isinfo.php |
| WinSW | MIT | https://github.com/winsw/winsw |
| PyInstaller | GPL-2.0 with bootloader exception | https://github.com/pyinstaller/pyinstaller |

Note on `PyInstaller` (GPL-2.0): PyInstaller's bootloader exception explicitly
allows distribution of the resulting executables under other licenses.
GuardianNode-built `.exe` files are AGPL-3.0 unless a separate commercial
license applies.

## External services (optional, not bundled)

| Service | Used for | Required? |
|---|---|---|
| Ollama | Local LLM runtime | Yes (pulled at install) |
| SMTP server | Email notifications | Optional, parent-configured |
| Pi-hole / AdGuard Home | Domain blocking | Optional integration |

Models pulled from Ollama have their own licenses. See [`MODEL_LICENSES.md`](MODEL_LICENSES.md).

## License compliance verification

Before release, review installed dependencies against
[`DEPENDENCY_POLICY.md`](DEPENDENCY_POLICY.md). A dedicated automated checker is
planned, but this source checkout does not currently include one.

## Reporting a missing notice

If you spot a dependency we should be acknowledging here, open an issue or PR.
