#!/usr/bin/env bash
# GuardianNode Linux server installer.
#
# Installs the GuardianNode backend as a systemd service, sets up Ollama,
# creates a 'guardiannode' system user, and points the parent at the
# first-run web setup wizard.
#
# Run with: curl -fsSL ... | sudo bash
#       or: sudo ./install.sh

set -euo pipefail

# ---------- Config ----------
GN_VERSION="${GN_VERSION:-0.1.0}"
GN_USER="guardiannode"
GN_HOME="/opt/guardiannode"
GN_DATA="/var/lib/guardiannode"
GN_LOG="/var/log/guardiannode"
GN_BIND_HOST="${GN_BIND_HOST:-0.0.0.0}"
GN_BIND_PORT="${GN_BIND_PORT:-8787}"
GN_REPO_URL="${GN_REPO_URL:-https://github.com/the-vibe-dev/guardiannode}"
GN_SRC_ZIP="${GN_SRC_ZIP:-}"     # if set, install from local zip instead of git
GN_NO_OLLAMA="${GN_NO_OLLAMA:-0}"

# ---------- Helpers ----------
red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    red "This installer must run as root. Use: sudo $0"
    exit 1
  fi
}

detect_distro() {
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_VERSION="${VERSION_ID:-}"
  else
    DISTRO_ID="unknown"
  fi
  green "Detected distro: $DISTRO_ID $DISTRO_VERSION"
}

install_system_packages() {
  blue "Installing system dependencies..."
  case "$DISTRO_ID" in
    ubuntu|debian|raspbian|linuxmint|pop)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq python3 python3-venv python3-pip sqlite3 curl ca-certificates git avahi-daemon libnss-mdns
      systemctl enable --now avahi-daemon || true
      ;;
    fedora|rhel|centos|rocky|almalinux)
      dnf install -y python3 python3-pip sqlite curl ca-certificates git avahi nss-mdns || \
        yum install -y python3 python3-pip sqlite curl git avahi nss-mdns
      systemctl enable --now avahi-daemon || true
      ;;
    arch|manjaro|endeavouros)
      pacman -Sy --noconfirm python python-pip sqlite curl ca-certificates git avahi nss-mdns
      systemctl enable --now avahi-daemon || true
      ;;
    opensuse*|sles)
      zypper -n install python3 python3-pip sqlite3 curl git avahi nss-mdns
      systemctl enable --now avahi-daemon || true
      ;;
    *)
      yellow "Unknown distro '$DISTRO_ID' — please install python3, pip, sqlite3, curl, git manually."
      ;;
  esac
}

create_user() {
  if id -u "$GN_USER" >/dev/null 2>&1; then
    green "User '$GN_USER' already exists."
  else
    blue "Creating system user '$GN_USER'..."
    useradd --system --shell /usr/sbin/nologin --home-dir "$GN_HOME" --create-home "$GN_USER"
  fi
  mkdir -p "$GN_DATA" "$GN_LOG" "$GN_HOME"
  chown -R "$GN_USER:$GN_USER" "$GN_DATA" "$GN_LOG" "$GN_HOME"
  chmod 700 "$GN_DATA"
}

fetch_source() {
  local target="$GN_HOME/src"
  if [ -n "$GN_SRC_ZIP" ] && [ -r "$GN_SRC_ZIP" ]; then
    blue "Extracting GuardianNode from $GN_SRC_ZIP ..."
    mkdir -p "$target"
    if command -v unzip >/dev/null; then
      unzip -q -o "$GN_SRC_ZIP" -d "$target"
    else
      tar -xzf "$GN_SRC_ZIP" -C "$target"
    fi
  else
    blue "Cloning $GN_REPO_URL into $target ..."
    rm -rf "$target"
    git clone --depth 1 "$GN_REPO_URL" "$target"
  fi
  chown -R "$GN_USER:$GN_USER" "$target"
}

install_backend() {
  blue "Setting up Python venv..."
  sudo -u "$GN_USER" python3 -m venv "$GN_HOME/venv"
  sudo -u "$GN_USER" "$GN_HOME/venv/bin/pip" install --quiet --upgrade pip
  sudo -u "$GN_USER" "$GN_HOME/venv/bin/pip" install --quiet -e "$GN_HOME/src/backend"
}

probe_hardware_and_pick_tier() {
  blue "Probing hardware to pick classifier tier..."
  local probe_out
  probe_out="$(sudo -u "$GN_USER" "$GN_HOME/venv/bin/python" \
    "$GN_HOME/src/agent-windows/src/hardware_probe.py" 2>/dev/null || true)"
  if [ -z "$probe_out" ]; then
    yellow "Hardware probe failed; defaulting to vision_only tier."
    GN_TIER="${GN_TIER:-vision_only}"
    GN_TEXT_MODEL="${GN_TEXT_MODEL:-}"
    GN_VISION_MODEL="${GN_VISION_MODEL:-qwen2.5vl:7b}"
    return
  fi
  GN_TIER="${GN_TIER:-$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["classifier_tier"])')}"
  GN_TEXT_MODEL="${GN_TEXT_MODEL:-$(echo "$probe_out"   | python3 -c 'import json,sys; print(json.load(sys.stdin).get("text_model") or "")')}"
  GN_VISION_MODEL="${GN_VISION_MODEL:-$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("vision_model") or "")')}"
  local reasoning
  reasoning="$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["reasoning"])')"
  green "Tier: $GN_TIER"
  green "Text model: ${GN_TEXT_MODEL:-(none)}"
  green "Vision model: ${GN_VISION_MODEL:-(none)}"
  yellow "$reasoning"
}

install_ollama() {
  if [ "$GN_NO_OLLAMA" = "1" ]; then
    yellow "Skipping Ollama install (GN_NO_OLLAMA=1)."
    return
  fi
  if [ "$GN_TIER" = "text_only" ] && [ -z "${GN_TEXT_MODEL:-}" ]; then
    yellow "text_only tier without LLM — skipping Ollama entirely."
    return
  fi
  # Tesseract is the CPU OCR engine for text_only tier (vision tiers use the LLM's OCR).
  if [ "$GN_TIER" = "text_only" ]; then
    blue "Installing tesseract-ocr for the CPU OCR path..."
    case "$DISTRO_ID" in
      ubuntu|debian|raspbian|linuxmint|pop) apt-get install -y -qq tesseract-ocr ;;
      fedora|rhel|centos|rocky|almalinux)   dnf install -y tesseract || yum install -y tesseract ;;
      arch|manjaro|endeavouros)             pacman -S --noconfirm tesseract tesseract-data-eng ;;
      opensuse*|sles)                       zypper -n install tesseract-ocr ;;
    esac
  fi
  # Shared bootstrap: installs Ollama if missing, pulls models per tier.
  blue "Configuring Ollama + pulling models for tier=$GN_TIER..."
  GN_TIER="$GN_TIER" \
  GN_TEXT_MODEL="${GN_TEXT_MODEL:-}" \
  GN_VISION_MODEL="${GN_VISION_MODEL:-}" \
  GN_OLLAMA_URL="${GN_OLLAMA_URL:-http://127.0.0.1:11434}" \
    bash "$GN_HOME/src/installer/shared/configure_ollama_linux.sh"
}

write_systemd_unit() {
  blue "Writing systemd unit..."
  cat > /etc/systemd/system/guardiannode-backend.service <<EOF
[Unit]
Description=GuardianNode Backend
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$GN_USER
Group=$GN_USER
Environment="GUARDIANNODE_DATA_DIR=$GN_DATA"
Environment="GUARDIANNODE_BIND_HOST=$GN_BIND_HOST"
Environment="GUARDIANNODE_BIND_PORT=$GN_BIND_PORT"
Environment="GUARDIANNODE_LOG_LEVEL=INFO"
Environment="GUARDIANNODE_CLASSIFIER_TIER=$GN_TIER"
Environment="GUARDIANNODE_TEXT_MODEL=${GN_TEXT_MODEL:-llama3.2:3b}"
Environment="GUARDIANNODE_VISION_MODEL=${GN_VISION_MODEL:-qwen2.5vl:7b}"
Environment="GUARDIANNODE_OLLAMA_URL=${GN_OLLAMA_URL:-http://127.0.0.1:11434}"
Environment="GUARDIANNODE_CLASSIFIER_TIMEOUT_SECONDS=120"
WorkingDirectory=$GN_HOME/src/backend
ExecStart=$GN_HOME/venv/bin/python -m uvicorn app.main:app --host $GN_BIND_HOST --port $GN_BIND_PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$GN_DATA $GN_LOG
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable guardiannode-backend.service
  systemctl restart guardiannode-backend.service
  green "Service installed and started."
}

wait_for_health() {
  local tries=0
  blue "Waiting for backend health check..."
  while [ $tries -lt 30 ]; do
    if curl -sf "http://127.0.0.1:$GN_BIND_PORT/api/health" >/dev/null; then
      green "Backend is healthy."
      return 0
    fi
    sleep 1
    tries=$((tries + 1))
  done
  red "Backend did not become healthy in 30s. Check logs: journalctl -u guardiannode-backend"
  return 1
}

print_done() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -z "$ip" ] && ip="127.0.0.1"
  echo
  green "=========================================="
  green "GuardianNode installed and running."
  green "=========================================="
  echo
  echo "Open the parent dashboard at:"
  echo
  echo "    http://${ip}:${GN_BIND_PORT}"
  echo
  echo "On the same machine you can also use:"
  echo "    http://127.0.0.1:${GN_BIND_PORT}"
  echo
  echo "First-run setup wizard appears automatically when no admin exists."
  echo
  echo "Service:    systemctl status guardiannode-backend"
  echo "Logs:       journalctl -u guardiannode-backend"
  echo "Data dir:   $GN_DATA"
  echo
  echo "mDNS:       service will announce itself as _guardiannode._tcp"
  echo "            on this network. The Windows child installer will"
  echo "            auto-discover this server."
  echo
}

main() {
  require_root
  detect_distro
  install_system_packages
  create_user
  fetch_source
  install_backend
  probe_hardware_and_pick_tier
  install_ollama
  write_systemd_unit
  wait_for_health || exit 1
  print_done
}

main "$@"
