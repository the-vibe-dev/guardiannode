# Linux server installer

Two ways to install:

## A) Native install (recommended for low-overhead deployments)

```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/main/installer/server-linux/install.sh | sudo bash
```

What it does:
1. Detects distro (apt/dnf/pacman/zypper)
2. Installs python3, sqlite, avahi (for mDNS)
3. Creates a `guardiannode` system user
4. Clones repo into `/opt/guardiannode/src/`
5. Builds a Python venv at `/opt/guardiannode/venv/`
6. Installs Ollama via its upstream installer
7. Registers `guardiannode-backend.service` as systemd
8. Starts the service and prints the dashboard URL

Open the printed URL in a browser to complete first-run setup (admin account + recovery code + AI model pull).

## B) Docker Compose (recommended for home-server enthusiasts)

```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

What it does:
- Spins up `ollama/ollama` for the LLM
- Spins up a `guardiannode_backend` container exposing port 8787
- Persists state in two Docker volumes: `ollama_models` and `gn_data`

To enable mDNS auto-discovery from the Windows child installer, the backend container runs with `network_mode: host`. Comment that out if you don't need auto-discovery.

For NVIDIA GPU support: install `nvidia-container-toolkit` on the host and uncomment the `deploy.resources` block in `docker-compose.yml`.

## Pulling models

After the backend is up, pull the default models:

```bash
# native install
sudo -u guardiannode ollama pull llama3.2:3b
sudo -u guardiannode ollama pull llava-phi3

# docker
docker exec guardiannode_ollama ollama pull llama3.2:3b
docker exec guardiannode_ollama ollama pull llava-phi3
```

Or use the web setup wizard at `http://<server-ip>:8787` which has a model picker.

## Uninstall

```bash
sudo systemctl disable --now guardiannode-backend
sudo rm /etc/systemd/system/guardiannode-backend.service
sudo userdel -r guardiannode
sudo rm -rf /opt/guardiannode /var/lib/guardiannode /var/log/guardiannode
sudo systemctl daemon-reload
```
