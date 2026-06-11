#!/usr/bin/env bash
# Cross-build the Windows installers from a Linux host using Wine + Inno Setup CLI.
#
# Output: installer/build/dist/*.exe
#
# Usage:
#   ./installer/build/build_all.sh                # builds both child + server installers
#   ./installer/build/build_all.sh --child-only
#   ./installer/build/build_all.sh --server-only
#
# Requirements (Linux host):
#   - wine 8+
#   - python3, npm
#   - curl, unzip
#
# This script:
#   1. Downloads & installs Inno Setup 6 into a project-local wine prefix
#   2. Builds the dashboard (npm run build)
#   3. Stages backend + agent Python source (not PyInstaller-bundled; see notes)
#   4. Stages WinSW wrapper exe
#   5. Compiles .iss → .exe via wine iscc.exe
#
# Notes about the agent payload:
#   The .iss expects pre-built PyInstaller bundles under build/stage/agent and
#   build/stage/backend. PyInstaller can be run under Wine if you have a Python
#   for Windows installed in the wine prefix. For a Linux-host build we ship
#   the Python source plus a "launcher.exe" stub that re-execs Windows Python
#   from the parent's PC. The official release builds run on a Windows runner
#   in CI to produce real PyInstaller bundles.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INST="$ROOT/installer"
BUILD="$INST/build"
STAGE="$BUILD/stage"
DIST="$BUILD/dist"
WINEPREFIX="$BUILD/.wine"
INNO_INSTALLER_URL="https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe"
INNO_INSTALLER="$BUILD/innosetup-6.7.1.exe"
WINSW_URL="https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
WINSW_EXE="$BUILD/WinSW-x64.exe"

BUILD_CHILD=1
BUILD_SERVER=1
while [ $# -gt 0 ]; do
  case "$1" in
    --child-only)  BUILD_SERVER=0;;
    --server-only) BUILD_CHILD=0;;
    -h|--help)
      sed -n '1,40p' "$0"; exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
  shift
done

green() { printf "\033[32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }

mkdir -p "$BUILD" "$STAGE" "$DIST"
mkdir -p "$STAGE/agent" "$STAGE/backend" "$STAGE/dashboard" "$STAGE/winsw"

# ---- 1. Download Inno Setup ----
if [ ! -f "$INNO_INSTALLER" ]; then
  blue "Downloading Inno Setup..."
  curl -fL --retry 3 -o "$INNO_INSTALLER" "$INNO_INSTALLER_URL"
fi

# ---- 2. Install Inno Setup into the project-local wine prefix ----
export WINEPREFIX
export WINEDEBUG=-all
export DISPLAY="${DISPLAY:-:0}"

find_iscc() {
  find "$WINEPREFIX/drive_c" -iname "ISCC.exe" -print -quit 2>/dev/null
}
ISCC_PATH="$(find_iscc || true)"
if [ -z "$ISCC_PATH" ] || [ ! -f "$ISCC_PATH" ]; then
  blue "Initializing wine prefix at $WINEPREFIX..."
  WINEARCH=win64 wineboot -i 2>&1 | tail -5 || true
  blue "Installing Inno Setup (silent)..."
  wine "$INNO_INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER 2>&1 | tail -3 || true
  sleep 1
  ISCC_PATH="$(find_iscc || true)"
fi

if [ -z "$ISCC_PATH" ] || [ ! -f "$ISCC_PATH" ]; then
  red "Inno Setup compiler not found anywhere under $WINEPREFIX/drive_c"
  red "Try installing Inno Setup manually:"
  red "  WINEPREFIX=$WINEPREFIX wine $INNO_INSTALLER"
  exit 1
fi
green "ISCC: $ISCC_PATH"

# Convert host path to a wine path
ISCC_WINE_PATH="$(WINEDEBUG=-all winepath -w "$ISCC_PATH" 2>/dev/null)"
if [ -z "$ISCC_WINE_PATH" ]; then
  ISCC_WINE_PATH='C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
fi

# ---- 3. Download WinSW ----
if [ ! -f "$WINSW_EXE" ]; then
  blue "Downloading WinSW..."
  curl -fL --retry 3 -o "$WINSW_EXE" "$WINSW_URL"
fi
cp "$WINSW_EXE" "$STAGE/winsw/WinSW.exe"
cp "$BUILD/winsw_templates/Watchdog.xml" "$STAGE/winsw/Watchdog.xml"
cp "$BUILD/winsw_templates/Backend.xml"  "$STAGE/winsw/Backend.xml"

# ---- 4. Build dashboard ----
blue "Building dashboard..."
( cd "$ROOT/dashboard" && npm install --silent && npm run build --silent )
rm -rf "$STAGE/dashboard"
mkdir -p "$STAGE/dashboard"
cp -r "$ROOT/dashboard/dist/." "$STAGE/dashboard/"

# ---- 5. Stage agent payload ----
# If a real PyInstaller bundle has been dropped at build/prebuilt/agent (with
# GuardianNodeAgent.exe + _internal/), use it. Otherwise fall back to staging
# Python source + .bat stubs (which require Python on the target machine and
# are only suitable for dev iteration, not real installs).
rm -rf "$STAGE/agent" "$STAGE/backend"
mkdir -p "$STAGE/agent" "$STAGE/backend"
PREBUILT_AGENT="$BUILD/prebuilt/agent"
if [ -f "$PREBUILT_AGENT/GuardianNodeAgent.exe" ] && [ -d "$PREBUILT_AGENT/_internal" ]; then
  blue "Staging prebuilt agent bundle from $PREBUILT_AGENT..."
  cp -r "$PREBUILT_AGENT/." "$STAGE/agent/"
else
  blue "Staging agent Python source + .bat stubs (no prebuilt bundle found)..."
  cp -r "$ROOT/agent-windows/src" "$STAGE/agent/src"
  cp -r "$ROOT/agent-windows/policies" "$STAGE/agent/policies"
  cp -r "$ROOT/agent-windows/ocr_regions" "$STAGE/agent/ocr_regions"
  cp    "$ROOT/agent-windows/pyproject.toml" "$STAGE/agent/pyproject.toml"
  cp    "$ROOT/agent-windows/README.md" "$STAGE/agent/README.md"
  cat > "$STAGE/agent/GuardianNodeAgent.exe.bat" <<'BAT'
@echo off
"%~dp0..\..\..\python\python.exe" -m src.main %*
BAT
  cat > "$STAGE/agent/GuardianNodeWatchdog.exe.bat" <<'BAT'
@echo off
"%~dp0..\..\..\python\python.exe" -m src.watchdog %*
BAT
  cat > "$STAGE/agent/GuardianNodeTray.exe.bat" <<'BAT'
@echo off
"%~dp0..\..\..\python\python.exe" -m src.tray_app %*
BAT
fi

cp -r "$ROOT/backend/app" "$STAGE/backend/app"
cp    "$ROOT/backend/pyproject.toml" "$STAGE/backend/pyproject.toml"
cp    "$ROOT/backend/README.md" "$STAGE/backend/README.md"
[ -f "$ROOT/backend/alembic.ini" ] && cp "$ROOT/backend/alembic.ini" "$STAGE/backend/alembic.ini" || true

# ---- 6. Ensure assets/icon.ico exists (placeholder) ----
ICON="$INST/child-device-windows/assets/icon.ico"
SRV_ICON="$INST/server-windows/assets/icon.ico"
if [ ! -f "$ICON" ] || [ ! -f "$SRV_ICON" ]; then
  blue "Generating placeholder icon..."
  python3 - <<PY
from PIL import Image, ImageDraw
import os
for path in ["$ICON", "$SRV_ICON"]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    images = []
    for (w,h) in sizes:
        img = Image.new('RGBA', (w,h), (255,255,255,0))
        d = ImageDraw.Draw(img)
        pad = w//8
        d.ellipse((pad,pad,w-pad,h-pad), fill=(46,125,50,255))
        images.append(img)
    images[0].save(path, format='ICO', sizes=sizes)
print('ok')
PY
fi

# ---- 7. Compile the .iss files ----
compile_iss() {
  local iss_relative="$1"
  local iss_path="$INST/$iss_relative"
  local label="$2"
  if [ ! -f "$iss_path" ]; then
    red "Missing .iss: $iss_path"
    return 1
  fi
  blue "Compiling $label ..."
  ( cd "$(dirname "$iss_path")" && \
    wine "$ISCC_WINE_PATH" "$(basename "$iss_path")" 2>&1 | tail -15 )
}

if [ $BUILD_CHILD -eq 1 ]; then
  compile_iss "child-device-windows/GuardianNodeChildSetup.iss" "Child Device installer"
fi
if [ $BUILD_SERVER -eq 1 ]; then
  compile_iss "server-windows/GuardianNodeServerSetup.iss" "Server installer"
fi

# ---- 8. Checksums ----
# Publish SHA-256 hashes for every release artifact so parents (and the
# SmartScreen walkthrough) can verify downloads. See docs/REPRODUCIBLE_BUILDS.md.
if ls "$DIST"/*.exe >/dev/null 2>&1; then
  blue "Generating SHA256SUMS ..."
  ( cd "$DIST" && sha256sum *.exe > SHA256SUMS )
  green "Wrote $DIST/SHA256SUMS"
fi

# ---- 9. Summarize ----
echo
green "==== BUILD OUTPUT ===="
ls -lh "$DIST"/*.exe 2>/dev/null || red "No .exe artifacts produced."
[ -f "$DIST/SHA256SUMS" ] && { echo; cat "$DIST/SHA256SUMS"; }
echo
green "Done. Distribute the .exe files (and SHA256SUMS) under $DIST/"
