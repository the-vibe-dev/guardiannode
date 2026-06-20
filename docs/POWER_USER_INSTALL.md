# Power-user Source Install

GuardianNode is designed so a technical parent can inspect, build, and run it
without trusting a black-box installer.

The normal release installer is still the easiest path. It starts the agent and
tray during install, registers all-user logon tasks so they launch for every
Windows account at sign-in, and pairs the child node with the server when a
pairing code is supplied.

## Trust checks

1. Download a release and compare it with `SHA256SUMS`.
2. Read the installer scripts in `installer/`.
3. Read the backend routes in `backend/app/api/`.
4. Search outbound network usage with:

```bash
rg "http://|https://|AsyncClient|requests|websocket" backend agent-windows dashboard installer
```

The intended default is local-first: the child node talks to your GuardianNode
backend, the backend talks to local Ollama, and no child data is uploaded to a
vendor cloud.

## Build the Windows child installer yourself

Prerequisites on Windows:

- Git
- Python 3.12 or 3.13
- Node.js LTS
- Inno Setup 6

Build the agent executables:

```powershell
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode\agent-windows
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[windows]" pyinstaller
.\.venv\Scripts\pyinstaller --clean --noconfirm guardiannode_agent.spec
.\scripts\verify_windows_bundle.ps1
```

Stage the bundle for the installer:

```powershell
cd ..
New-Item -ItemType Directory -Force installer\build\prebuilt\agent | Out-Null
Copy-Item agent-windows\dist\GuardianNodeAgent\* installer\build\prebuilt\agent -Recurse -Force
```

Compile `installer\child-device-windows\GuardianNodeChildSetup.iss` with Inno
Setup. The output is `GuardianNodeChildSetup-<version>.exe`.

For separated installs, the installer can be scripted with:

```cmd
GuardianNodeChildSetup-0.1.0-alpha.1.exe /VERYSILENT /MODE=separated /SERVERURL=http://192.168.1.42:8787 /PAIRCODE=506755
```

The pairing code must be generated from the parent dashboard first. Codes expire
and are one-time use.

## Build installers from Linux

The Linux build script uses Wine and Inno Setup:

```bash
sudo apt-get install -y wine python3 python3-venv nodejs npm curl unzip
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode
./installer/build/build_all.sh --child-only
cd installer/build/dist
sha256sum *.exe > SHA256SUMS
```

For official releases, use a fresh Windows-built PyInstaller agent bundle in
`installer/build/prebuilt/agent` before compiling the child installer.

## Run the child node from Python

This is useful for auditing and testing. It is not as tamper-resistant as the
installer because it does not install the service/watchdog wrappers.

On the child PC:

```powershell
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode\agent-windows
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[windows]"
.\.venv\Scripts\python -m src.main --pair --server http://<server-ip>:8787 --code <pair-code>
.\.venv\Scripts\python -m src.main
```

In a second terminal, start the tray:

```powershell
.\.venv\Scripts\python -m src.tray_app
```

To launch from source whenever any Windows account signs in, add `.cmd` files to
`C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup`. Use fully quoted
paths:

```cmd
@echo off
cd /d "C:\path\to\guardiannode\agent-windows"
start "GuardianNode Agent" "C:\path\to\guardiannode\agent-windows\.venv\Scripts\python.exe" -m src.main
```

Create a second file for the tray:

```cmd
@echo off
cd /d "C:\path\to\guardiannode\agent-windows"
start "GuardianNode Tray" "C:\path\to\guardiannode\agent-windows\.venv\Scripts\python.exe" -m src.tray_app
```

## Install the Linux backend

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.1/installer/server-linux/install.sh | sudo bash
```

For test systems without model downloads:

```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.1/installer/server-linux/install.sh | sudo GN_NO_OLLAMA=1 bash
```

After install, open `http://<server-ip>:8787/setup`, create the admin account,
then use **Devices -> Add device** to generate the pairing code for the child
node.
