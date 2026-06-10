#!/usr/bin/env bash
# GuardianNode — Linux Ollama bootstrap.
#
# Called by install.sh after hardware probe has picked a tier.
# Receives env vars:
#   GN_TIER         = full | vision_only | text_only
#   GN_TEXT_MODEL   = ollama tag (optional; defaults from tier)
#   GN_VISION_MODEL = ollama tag (optional)
#   GN_OLLAMA_URL   = http://host:port (defaults to local)

set -uo pipefail

TIER="${GN_TIER:-vision_only}"
OLLAMA_URL="${GN_OLLAMA_URL:-http://127.0.0.1:11434}"
TEXT_MODEL="${GN_TEXT_MODEL:-}"
VISION_MODEL="${GN_VISION_MODEL:-}"
LOG="/var/log/guardiannode/install-ollama.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

# Pick default models per tier
if [ -z "$TEXT_MODEL" ]; then
  case "$TIER" in
    full)        TEXT_MODEL="llama3.2:3b" ;;
    text_only)   TEXT_MODEL="llama3.2:1b" ;;
    vision_only) TEXT_MODEL="" ;;
  esac
fi
if [ -z "$VISION_MODEL" ]; then
  case "$TIER" in
    full|vision_only) VISION_MODEL="qwen2.5vl:7b" ;;
    text_only)        VISION_MODEL="" ;;
  esac
fi

log "Tier: $TIER  TextModel: '$TEXT_MODEL'  VisionModel: '$VISION_MODEL'  OllamaUrl: $OLLAMA_URL"

ollama_reachable() {
  curl -sf --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null
}

install_ollama() {
  log "Ollama not reachable. Installing via official script ..."
  if ! command -v curl >/dev/null; then
    log "ERROR: curl missing. apt/dnf install it first."
    return 1
  fi
  curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tee -a "$LOG"
  sleep 5
  # Persist env so models stay loaded across restarts
  local override="/etc/systemd/system/ollama.service.d"
  mkdir -p "$override"
  cat > "$override/keepalive.conf" <<EOF
[Service]
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_MAX_LOADED_MODELS=3"
EOF
  systemctl daemon-reload || true
  systemctl restart ollama || true
  # Wait for it to come back up
  for i in $(seq 1 30); do
    if ollama_reachable; then return 0; fi
    sleep 2
  done
  return 1
}

installed_models() {
  curl -sf --max-time 10 "$OLLAMA_URL/api/tags" 2>/dev/null \
    | python3 -c "import json,sys; print('\n'.join(m['name'] for m in json.load(sys.stdin).get('models',[])))" \
    2>/dev/null
}

pull_model() {
  local model="$1"
  if [ -z "$model" ]; then return 0; fi
  if installed_models | grep -qx "$model"; then
    log "Model '$model' already installed."
    return 0
  fi
  log "Pulling model '$model' (this can take several minutes) ..."
  curl -sf --max-time 1800 -X POST "$OLLAMA_URL/api/pull" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$model\",\"stream\":false}" \
    >/dev/null 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then
    log "Pull '$model' succeeded."
    return 0
  else
    log "ERROR pulling '$model' (exit $rc)"
    return 1
  fi
}

# --- Main ---

if [ "$TIER" = "text_only" ] && [ -z "$TEXT_MODEL" ]; then
  log "text_only tier with no LLM. Skipping Ollama setup entirely."
  exit 0
fi

# Only install Ollama if the URL is local
case "$OLLAMA_URL" in
  http://127.0.0.1:*|http://localhost:*)
    if ! ollama_reachable; then
      install_ollama || { log "Ollama install/start failed."; exit 2; }
    else
      log "Ollama already running locally."
    fi
    ;;
  *)
    if ! ollama_reachable; then
      log "Remote Ollama at $OLLAMA_URL unreachable; continuing — backend will retry at runtime."
    else
      log "Remote Ollama reachable."
    fi
    ;;
esac

rc=0
[ -n "$TEXT_MODEL" ]   && { pull_model "$TEXT_MODEL"   || rc=1; }
[ -n "$VISION_MODEL" ] && { pull_model "$VISION_MODEL" || rc=1; }
exit $rc
