#!/usr/bin/env bash
# GuardianNode Linux server installer.
#
# Installs the GuardianNode backend as a systemd service, sets up Ollama,
# creates a 'guardiannode' system user, and points the parent at the
# first-run web setup wizard.
#
# Download, verify the published checksum/signature, review locally, then run:
#   sudo ./install.sh

set -Eeuo pipefail

# ---------- Config ----------
GN_VERSION="${GN_VERSION:-v0.1.0-alpha.1}"
GN_USER="${GN_USER:-guardiannode}"
GN_HOME="${GN_HOME:-/opt/guardiannode}"
GN_DATA="${GN_DATA:-/var/lib/guardiannode}"
GN_LOG="${GN_LOG:-/var/log/guardiannode}"
GN_BIND_HOST="${GN_BIND_HOST:-127.0.0.1}"
GN_BIND_PORT="${GN_BIND_PORT:-8787}"
GN_REPO_URL="${GN_REPO_URL:-https://github.com/the-vibe-dev/guardiannode}"
GN_SRC_ZIP="${GN_SRC_ZIP:-}"     # if set, install from local zip instead of git
GN_SRC_SHA256="${GN_SRC_SHA256:-}" # optional sha256 for GN_SRC_ZIP
GN_NO_OLLAMA="${GN_NO_OLLAMA:-0}"
GN_RELEASE_ID="${GN_RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
GN_STAGED_SRC=""
GN_STAGED_VENV=""
GN_PREV_SRC=""
GN_PREV_VENV=""

# ---------- Helpers ----------
red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

var_is_set() {
  eval '[ "${'"$1"'+x}" = "x" ]'
}

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
      apt-get install -y -qq python3 python3-venv python3-pip sqlite3 curl ca-certificates git unzip avahi-daemon libnss-mdns tesseract-ocr
      systemctl enable --now avahi-daemon || true
      ;;
    fedora|rhel|centos|rocky|almalinux)
      dnf install -y python3 python3-pip sqlite curl ca-certificates git unzip avahi nss-mdns tesseract || \
        yum install -y python3 python3-pip sqlite curl git unzip avahi nss-mdns tesseract
      systemctl enable --now avahi-daemon || true
      ;;
    arch|manjaro|endeavouros)
      pacman -Sy --noconfirm python python-pip sqlite curl ca-certificates git unzip avahi nss-mdns tesseract tesseract-data-eng
      systemctl enable --now avahi-daemon || true
      ;;
    opensuse*|sles)
      zypper -n install python3 python3-pip sqlite3 curl git unzip avahi nss-mdns tesseract-ocr
      systemctl enable --now avahi-daemon || true
      ;;
    *)
      yellow "Unknown distro '$DISTRO_ID' — please install python3, pip, sqlite3, curl, git, and Tesseract OCR manually."
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

create_setup_token() {
  blue "Creating one-time setup token..."
  local token_path="$GN_DATA/keys/setup_token.json"
  mkdir -p "$GN_DATA/keys"
  local token
  token="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  python3 - "$token_path" "$token" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone
path, token = sys.argv[1], sys.argv[2]
expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
with open(path, "w", encoding="utf-8") as f:
    json.dump({"token": token, "expires_at": expires_at.isoformat()}, f)
PY
  chown "$GN_USER:$GN_USER" "$token_path"
  chmod 600 "$token_path"
  GN_SETUP_TOKEN="$token"
}

verify_source_checksum() {
  if [ -z "$GN_SRC_SHA256" ]; then
    return
  fi
  if [ -z "$GN_SRC_ZIP" ] || [ ! -r "$GN_SRC_ZIP" ]; then
    red "GN_SRC_SHA256 was set, but GN_SRC_ZIP is not readable."
    exit 1
  fi
  blue "Verifying source archive checksum..."
  local actual
  actual="$(sha256sum "$GN_SRC_ZIP" | awk '{print $1}')"
  if [ "$actual" != "$GN_SRC_SHA256" ]; then
    red "Source archive checksum mismatch. Expected $GN_SRC_SHA256 but got $actual."
    exit 1
  fi
}

validate_source_tree() {
  local src="$1"
  local missing=0
  for path in LICENSE VERSION backend/pyproject.toml backend/app/main.py installer/shared/configure_ollama_linux.sh; do
    if [ ! -e "$src/$path" ]; then
      red "Source archive is missing required path: $path"
      missing=1
    fi
  done
  if [ "$missing" -ne 0 ]; then
    return 1
  fi
}

normalize_extracted_source() {
  local extract_dir="$1"
  local target="$2"
  local candidate="$extract_dir"
  local entries=()
  local entry
  while IFS= read -r entry; do
    entries+=("$entry")
  done < <(find "$extract_dir" -mindepth 1 -maxdepth 1 ! -name "__MACOSX" | sort)

  if [ "${#entries[@]}" -eq 1 ] && [ -d "${entries[0]}" ] && [ -d "${entries[0]}/backend" ]; then
    candidate="${entries[0]}"
  fi

  validate_source_tree "$candidate"
  mkdir -p "$target"
  (
    shopt -s dotglob nullglob
    mv "$candidate"/* "$target"/
  )
}

fetch_source() {
  local stage_root="$GN_HOME/staging/source-$GN_RELEASE_ID"
  GN_STAGED_SRC="$stage_root/src"
  if [ -e "$stage_root" ]; then
    local archived_stage="$GN_HOME/archived-src/stale-stage-$GN_RELEASE_ID"
    yellow "Moving existing staging directory to $archived_stage ..."
    mkdir -p "$(dirname "$archived_stage")"
    mv "$stage_root" "$archived_stage"
  fi
  mkdir -p "$stage_root"

  if [ -n "$GN_SRC_ZIP" ] && [ -r "$GN_SRC_ZIP" ]; then
    verify_source_checksum
    blue "Staging GuardianNode source from $GN_SRC_ZIP ..."
    local extract_dir="$stage_root/extract"
    mkdir -p "$extract_dir"
    case "$GN_SRC_ZIP" in
      *.zip)
        if ! command -v unzip >/dev/null; then
          red "unzip is required for .zip source archives."
          exit 1
        fi
        unzip -q "$GN_SRC_ZIP" -d "$extract_dir"
        ;;
      *.tar.gz|*.tgz)
        tar -xzf "$GN_SRC_ZIP" -C "$extract_dir"
        ;;
      *)
        red "Unsupported source archive extension: $GN_SRC_ZIP"
        exit 1
        ;;
    esac
    normalize_extracted_source "$extract_dir" "$GN_STAGED_SRC"
  else
    blue "Cloning $GN_REPO_URL ($GN_VERSION) into staging ..."
    git clone --depth 1 --branch "$GN_VERSION" "$GN_REPO_URL" "$GN_STAGED_SRC"
    validate_source_tree "$GN_STAGED_SRC"
  fi
  chown -R "$GN_USER:$GN_USER" "$stage_root"
}

install_backend() {
  blue "Setting up staged Python venv..."
  GN_STAGED_VENV="$GN_HOME/staging/venv-$GN_RELEASE_ID"
  if [ -e "$GN_STAGED_VENV" ]; then
    local archived_venv="$GN_HOME/archived-venv/stale-stage-$GN_RELEASE_ID"
    yellow "Moving existing staged venv to $archived_venv ..."
    mkdir -p "$(dirname "$archived_venv")"
    mv "$GN_STAGED_VENV" "$archived_venv"
  fi
  sudo -u "$GN_USER" python3 -m venv "$GN_STAGED_VENV"
  sudo -u "$GN_USER" "$GN_STAGED_VENV/bin/pip" install --quiet --upgrade pip
  sudo -u "$GN_USER" "$GN_STAGED_VENV/bin/pip" install --quiet -e "$GN_STAGED_SRC/backend"
  sudo -u "$GN_USER" "$GN_STAGED_VENV/bin/python" - <<'PY'
import importlib
importlib.import_module("app.main")
PY
}

activate_release() {
  blue "Activating staged source and virtualenv..."
  mkdir -p "$GN_HOME/archived-src" "$GN_HOME/archived-venv"
  if [ -e "$GN_HOME/src" ] || [ -L "$GN_HOME/src" ]; then
    GN_PREV_SRC="$GN_HOME/archived-src/previous-$GN_RELEASE_ID"
    mv "$GN_HOME/src" "$GN_PREV_SRC"
  fi
  if [ -e "$GN_HOME/venv" ] || [ -L "$GN_HOME/venv" ]; then
    GN_PREV_VENV="$GN_HOME/archived-venv/previous-$GN_RELEASE_ID"
    mv "$GN_HOME/venv" "$GN_PREV_VENV"
  fi
  mv "$GN_STAGED_SRC" "$GN_HOME/src"
  mv "$GN_STAGED_VENV" "$GN_HOME/venv"
  chown -R "$GN_USER:$GN_USER" "$GN_HOME/src" "$GN_HOME/venv"
}

rollback_release() {
  yellow "Rolling back to previous source/venv, if available..."
  local failed_id
  failed_id="$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -e "$GN_HOME/src" ] || [ -L "$GN_HOME/src" ]; then
    mkdir -p "$GN_HOME/archived-src"
    mv "$GN_HOME/src" "$GN_HOME/archived-src/failed-$failed_id"
  fi
  if [ -e "$GN_HOME/venv" ] || [ -L "$GN_HOME/venv" ]; then
    mkdir -p "$GN_HOME/archived-venv"
    mv "$GN_HOME/venv" "$GN_HOME/archived-venv/failed-$failed_id"
  fi
  if [ -n "$GN_PREV_SRC" ] && [ -e "$GN_PREV_SRC" ]; then
    mv "$GN_PREV_SRC" "$GN_HOME/src"
  fi
  if [ -n "$GN_PREV_VENV" ] && [ -e "$GN_PREV_VENV" ]; then
    mv "$GN_PREV_VENV" "$GN_HOME/venv"
  fi
  chown -R "$GN_USER:$GN_USER" "$GN_HOME/src" "$GN_HOME/venv" 2>/dev/null || true
  return 0
}

probe_hardware_and_pick_tier() {
  blue "Probing hardware to pick classifier tier..."
  local probe_out
  probe_out="$(sudo -u "$GN_USER" "$GN_HOME/venv/bin/python" \
    "$GN_HOME/src/agent-windows/src/hardware_probe.py" 2>/dev/null || true)"
  if [ -z "$probe_out" ]; then
    yellow "Hardware probe failed; defaulting conservatively to text_only without model pulls."
    if ! var_is_set GN_TIER; then
      GN_TIER="text_only"
    fi
    if ! var_is_set GN_TEXT_MODEL; then
      GN_TEXT_MODEL=""
    fi
    if ! var_is_set GN_VISION_MODEL; then
      GN_VISION_MODEL=""
    fi
    return
  fi
  if ! var_is_set GN_TIER; then
    GN_TIER="$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["classifier_tier"])')"
  fi
  if ! var_is_set GN_TEXT_MODEL; then
    GN_TEXT_MODEL="$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("text_model") or "")')"
  fi
  if ! var_is_set GN_VISION_MODEL; then
    GN_VISION_MODEL="$(echo "$probe_out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("vision_model") or "")')"
  fi
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
  local unit_path="${GN_SYSTEMD_UNIT_PATH:-/etc/systemd/system/guardiannode-backend.service}"
  mkdir -p "$(dirname "$unit_path")"
  cat > "$unit_path" <<EOF
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
Environment="GUARDIANNODE_MDNS_ENABLED=false"
Environment="GUARDIANNODE_LOG_LEVEL=INFO"
Environment="GUARDIANNODE_CLASSIFIER_TIER=$GN_TIER"
Environment="GUARDIANNODE_TEXT_MODEL=${GN_TEXT_MODEL-}"
Environment="GUARDIANNODE_VISION_MODEL=${GN_VISION_MODEL-}"
Environment="GUARDIANNODE_OLLAMA_URL=${GN_OLLAMA_URL:-http://127.0.0.1:11434}"
Environment="GUARDIANNODE_CLASSIFIER_TIMEOUT_SECONDS=120"
Environment="GUARDIANNODE_VISION_NUM_CTX=8192"
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
  echo "    http://127.0.0.1:${GN_BIND_PORT}"
  echo
  echo "One-time setup token:"
  echo
  echo "    ${GN_SETUP_TOKEN:-read $GN_DATA/keys/setup_token.json}"
  echo
  echo "First-run setup is loopback-only. Finish setup on this server first,"
  echo "then manually set GUARDIANNODE_BIND_HOST=0.0.0.0 plus an explicit"
  echo "GUARDIANNODE_ALLOWED_HOSTS list for the LAN IP/hostname child agents"
  echo "will use. Add a firewall rule only for a trusted LAN/VPN."
  echo
  echo "Service:    systemctl status guardiannode-backend"
  echo "Logs:       journalctl -u guardiannode-backend"
  echo "Data dir:   $GN_DATA"
  echo
  echo "mDNS:       disabled for fresh setup until LAN access is enabled."
  echo
}

main() {
  require_root
  detect_distro
  install_system_packages
  create_user
  create_setup_token
  fetch_source
  install_backend
  activate_release
  trap 'rollback_release' ERR
  probe_hardware_and_pick_tier
  install_ollama
  write_systemd_unit
  wait_for_health
  trap - ERR
  print_done
}

if [ "${GN_INSTALLER_LIBRARY_ONLY:-0}" != "1" ]; then
  main "$@"
fi
