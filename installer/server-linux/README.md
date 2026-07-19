# Linux server installer

Two ways to install:

## A) Native install (recommended for low-overhead deployments)

For alpha maintainer testing, download the tagged script, verify its published
SHA-256 or signature, review it locally, then run it with `sudo`. Avoid piping
an unverified network response directly into a privileged shell.

```bash
curl -fsSLO https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.2/installer/server-linux/install.sh
# Verify the published checksum or signature before running:
sudo bash install.sh
```

What it does:
1. Detects distro (apt/dnf/pacman/zypper)
2. Installs python3, sqlite, avahi packages, and Tesseract
3. Creates a `guardiannode` system user
4. Stages source from git or `GN_SRC_ZIP`, accepting both flat and
   GitHub-style top-level archive layouts
5. Builds and import-checks a staged Python venv before replacing the live
   `/opt/guardiannode/src/` and `/opt/guardiannode/venv/`
6. Archives the previous source/venv and rolls them back if the new service
   fails its health check
7. Installs Ollama via its upstream installer when needed
8. Registers `guardiannode-backend.service` as systemd
9. Starts the service and prints the local dashboard URL plus one-time setup token

Open the printed loopback URL in a browser on the server to complete first-run
setup (admin account + recovery code). Fresh installs do not bind to the LAN.
For this alpha, enabling a separated-server deployment is a manual admin task:
set both `GUARDIANNODE_BIND_HOST=0.0.0.0` and an explicit
`GUARDIANNODE_ALLOWED_HOSTS` list in the systemd environment override, restart
`guardiannode-backend`, and add an explicit firewall rule only for your trusted
LAN or VPN.

```text
GUARDIANNODE_BIND_HOST=0.0.0.0
GUARDIANNODE_ALLOWED_HOSTS=192.168.1.42,guardian-server,127.0.0.1,localhost
```

Replace the example IP/hostname with the exact LAN address/name child agents
will use.

## B) Docker Compose (recommended for home-server enthusiasts)

```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

What it does:
- Builds Tesseract plus qualified English language data into the backend
- Runs a fail-closed pipeline initializer before starting the backend
- Builds a backend image from explicit Node/Python base-image tags and runs it
  as non-root UID/GID `10001:10001`
- Runs the backend with `read_only: true`, dropped Linux capabilities,
  `no-new-privileges`, a bounded `/tmp` tmpfs, a healthcheck, and resource hints
- Spins up a `guardiannode_backend` container exposing port 8787 on loopback
- Starts Ollama and automatically pulls or verifies the configured text model
- Persists backend state in `gn_data`

The default closed-beta mode is `text_llm`. A normal Compose startup starts
Ollama automatically, and the initializer pulls or verifies the configured
model before the backend can start and readiness can pass:

```bash
docker compose up --build -d
```

For a deterministic rules-only deployment, explicitly set
`GUARDIANNODE_CLASSIFIER_MODE=rules_only`; this skips model classification.

The default English text-LLM Compose path is a closed-beta candidate and its
clean OCR-to-alert canary is required in CI. Docker vision/full modes remain
experimental. Optional OCR packs can be built
with `--build-arg TESSERACT_LANGS="eng spa"` and must also be listed in
`GUARDIANNODE_OCR_LANGUAGES`; only `eng` is currently platform-qualified.

The default Compose file uses normal bridge networking and publishes
`127.0.0.1:8787:8787`. mDNS discovery is advisory only in this alpha; child
devices should be configured with an explicit server URL. If you need host
networking on a Linux host after setup, use the host-network override:

```bash
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d
```

The host-network override requires `GUARDIANNODE_ALLOWED_HOSTS` in your shell,
uses Docker Compose's `!reset` tag, and requires Docker Compose v2.24 or newer.
Host networking exposes the backend according to `GUARDIANNODE_BIND_HOST` and
the host firewall, so use it only on a trusted LAN/VPN after first-run setup.

Do not expose the backend directly to the public internet. Use a trusted LAN,
Tailscale/WireGuard, or a reverse proxy with TLS and access controls.

Base and Ollama images are pinned by tag and manifest digest. Before a stable
release, publish GuardianNode-built images with SBOM and provenance
attestations.

For NVIDIA GPU support: install `nvidia-container-toolkit` on the host and uncomment the `deploy.resources` block in `docker-compose.yml`.

## Managing models

The Docker initializer automatically pulls the model required by the selected
classifier mode. For native installs, or to prefetch an additional model
manually, use:

```bash
# native install
sudo -u guardiannode ollama pull llama3.2:3b
sudo -u guardiannode ollama pull qwen3-vl:8b-instruct

# docker (optional manual prefetch)
docker exec guardiannode_ollama ollama pull llama3.2:3b
docker exec guardiannode_ollama ollama pull qwen3-vl:8b-instruct
```

Then open `http://127.0.0.1:8787/models` after setup to confirm the text and
vision endpoints can see the installed models.

## Uninstall

```bash
sudo systemctl disable --now guardiannode-backend
archive="/root/guardiannode-uninstall-$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$archive"
sudo mv /etc/systemd/system/guardiannode-backend.service "$archive"/
sudo userdel guardiannode
sudo mv /opt/guardiannode /var/lib/guardiannode /var/log/guardiannode "$archive"/
sudo systemctl daemon-reload
```
