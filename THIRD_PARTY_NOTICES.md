# Third-Party Notices

GuardianNode bundles or directly depends on the following third-party
components. Each component retains its original license.

<!-- third-party-notices:acknowledged
backend: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, alembic, cryptography, argon2-cffi, httpx, python-multipart, pyyaml, zeroconf, qrcode, pillow, pytesseract, python-ulid, itsdangerous, jinja2
agent: httpx, pyyaml, psutil, mss, pillow, pydantic, argon2-cffi, cryptography, python-ulid, zeroconf, pywin32, pystray, opencv-python, pytesseract
dashboard: @fontsource/inter, @fontsource/sora, react, react-dom, react-router-dom
other: inno setup, winsw, pyinstaller, ollama
-->

## Backend Runtime Dependencies (Python)

| Component | License | Project |
|---|---|---|
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| pydantic-settings | MIT | https://github.com/pydantic/pydantic-settings |
| SQLAlchemy | MIT | https://www.sqlalchemy.org/ |
| Alembic | MIT | https://alembic.sqlalchemy.org/ |
| cryptography | Apache-2.0 / BSD-3-Clause | https://github.com/pyca/cryptography |
| argon2-cffi | MIT | https://github.com/hynek/argon2-cffi |
| httpx | BSD-3-Clause | https://github.com/encode/httpx |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| PyYAML | MIT | https://github.com/yaml/pyyaml |
| zeroconf | LGPL-2.1 | https://github.com/python-zeroconf/python-zeroconf |
| qrcode | BSD-3-Clause | https://github.com/lincolnloop/python-qrcode |
| Pillow | HPND | https://python-pillow.org/ |
| pytesseract | Apache-2.0 | https://github.com/madmaze/pytesseract |
| python-ulid | MIT | https://github.com/mdomke/python-ulid |
| itsdangerous | BSD-3-Clause | https://github.com/pallets/itsdangerous |
| Jinja2 | BSD-3-Clause | https://github.com/pallets/jinja |

Note on `zeroconf` (LGPL-2.1): GuardianNode uses it as an unmodified Python
package via PyPI. Operators can disable mDNS or replace the package in a source
deployment if their compliance requirements demand it.

## Windows Agent Dependencies (Python)

| Component | License | Project |
|---|---|---|
| httpx | BSD-3-Clause | https://github.com/encode/httpx |
| PyYAML | MIT | https://github.com/yaml/pyyaml |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| mss | MIT | https://github.com/BoboTiG/python-mss |
| Pillow | HPND | https://python-pillow.org/ |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| argon2-cffi | MIT | https://github.com/hynek/argon2-cffi |
| cryptography | Apache-2.0 / BSD-3-Clause | https://github.com/pyca/cryptography |
| python-ulid | MIT | https://github.com/mdomke/python-ulid |
| zeroconf | LGPL-2.1 | https://github.com/python-zeroconf/python-zeroconf |
| pywin32 | PSF-2.0 | https://github.com/mhammond/pywin32 |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| opencv-python | Apache-2.0 | https://github.com/opencv/opencv-python |
| pytesseract | Apache-2.0 | https://github.com/madmaze/pytesseract |

Note on `pystray` (LGPL-3.0): GuardianNode uses it as an unmodified package.

## Dashboard Runtime Dependencies (Node)

| Component | License | Project |
|---|---|---|
| @fontsource/inter | OFL-1.1 | https://github.com/fontsource/font-files/tree/main/fonts/google/inter |
| @fontsource/sora | OFL-1.1 | https://github.com/fontsource/font-files/tree/main/fonts/google/sora |
| React | MIT | https://github.com/facebook/react |
| React DOM | MIT | https://github.com/facebook/react |
| React Router DOM | MIT | https://github.com/remix-run/react-router |

Bundled font license texts are included at:

- [`licenses/Inter-OFL-1.1.txt`](licenses/Inter-OFL-1.1.txt)
- [`licenses/Sora-OFL-1.1.txt`](licenses/Sora-OFL-1.1.txt)

## Installer, Build, And Service Wrappers

| Component | License | Project |
|---|---|---|
| Inno Setup | Modified BSD | https://jrsoftware.org/isinfo.php |
| WinSW | MIT | https://github.com/winsw/winsw |
| PyInstaller | GPL-2.0 with bootloader exception | https://github.com/pyinstaller/pyinstaller |

Note on `PyInstaller` (GPL-2.0): PyInstaller's bootloader exception explicitly
allows distribution of the resulting executables under other licenses.
GuardianNode-built executables are AGPL-3.0 unless a separate commercial
license applies.

## External Services And Models

| Service | Used for | Required? |
|---|---|---|
| Ollama | Local LLM runtime | Required for model-backed classification |
| SMTP server | Email notifications | Optional, parent-configured |
| Pi-hole / AdGuard Home | Domain blocking | Optional integration |

Models pulled from Ollama have their own licenses. See
[`MODEL_LICENSES.md`](MODEL_LICENSES.md).

## License Compliance Verification

Before release, run:

```bash
python scripts/check_third_party_notices.py
```

Also review installed dependency metadata against
[`DEPENDENCY_POLICY.md`](DEPENDENCY_POLICY.md), especially before publishing
binary installers or containers.

## Reporting A Missing Notice

If you spot a dependency we should acknowledge here, open an issue or PR.
