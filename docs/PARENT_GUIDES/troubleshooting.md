# Troubleshooting

## Installer

### "Windows protected your PC"
See [When Windows says "Protected your PC"](when-windows-says-protected-your-pc.md).
This is expected for unsigned alpha builds; verify the release source and hash
before continuing.

### "User Account Control" loops
The installer needs admin rights. If clicking Yes doesn't proceed:
1. Right-click `GuardianNodeChildSetup-0.1.0-alpha.1.exe` → **Run as administrator**.
2. If that fails, your Windows account isn't an Administrator. Sign in as the Administrator user first, then run the installer.

### Install fails with "Could not download Ollama"
Your network may be blocking the download. Either:
- Install Ollama manually from https://ollama.com/download — restart the GuardianNode installer, it will skip the Ollama step.
- Use the all-in-one installer on a different network, then move the PC.

### Install fails with "Could not pull model"
Same as above — your network is blocking the model pull. After install, manually run from PowerShell:
```powershell
ollama pull llama3.2:3b
ollama pull llava-phi3
```
Then restart the GuardianNode backend service: `sc stop GuardianNodeBackend && sc start GuardianNodeBackend`.

## Dashboard

### Dashboard URL refuses to connect
1. Open Services (Win + R, type `services.msc`).
2. Find **GuardianNode Backend**. Status should be **Running**.
3. If not, right-click → **Start**. If it fails to start, check the log at `C:\ProgramData\GuardianNode\logs\backend.log`.

### "Cannot connect to Ollama"
Open PowerShell and run:
```powershell
curl http://127.0.0.1:11434/api/tags
```
If that fails, Ollama isn't running. Start it via the Ollama tray icon, or run `ollama serve` from a terminal.

### Dashboard shows the device as offline
- Confirm the kid's PC is on and connected to the network.
- Open Services → **GuardianNode Agent** → should be Running.
- Check `C:\ProgramData\GuardianNode\logs\agent.log` for connection errors.
- If you're in separated mode, verify the server IP hasn't changed (router DHCP). Pin the server's IP in your router's DHCP settings.

## Agent

### Tray icon is missing
The tray app runs in the user session, not as a service. If it crashed:
1. Start menu → search "GuardianNode Tray" → click to relaunch.
2. To make it auto-start on login, the installer added a Start Menu Startup shortcut by default.

### Tray icon is red
Red means the agent can't reach the backend. Hover over the icon for the specific error.

### "Kill agent" / Task Manager → it comes back
That's the watchdog working as designed. The agent and watchdog restart each other. To stop them legitimately, pause monitoring or uninstall GuardianNode from an administrator account.

### Antivirus flagged the agent
Some antivirus products flag PyInstaller-bundled apps as suspicious because the technique is sometimes used by malware. Add GuardianNode to your AV exception list:
- Defender: `Settings → Update & Security → Windows Security → Virus & threat protection → Manage settings → Exclusions → Add an exclusion → Folder → C:\Program Files\GuardianNode`
- Other AVs: refer to their docs

Until we have a code-signing cert, this is unfortunately a recurring issue.

## Uninstall

### "I want to uninstall"
Use Windows Settings or Programs & Features from an administrator account. The alpha does not ship a tested password-gated uninstaller wrapper.

### Uninstall hangs or fails partway
1. Reboot the PC.
2. Run `GuardianNodeChildSetup-0.1.0-alpha.1.exe` again — the installer detects an existing install and offers **Repair** and **Uninstall** options.
3. If that fails, manually:
   - Stop services: `sc stop GuardianNodeWatchdog && sc stop GuardianNodeAgent && sc stop GuardianNodeBackend`
   - Delete services: `sc delete GuardianNodeWatchdog && sc delete GuardianNodeAgent && sc delete GuardianNodeBackend`
   - Delete folder: `Remove-Item -Recurse -Force "C:\Program Files\GuardianNode"`
   - Delete data: `Remove-Item -Recurse -Force "C:\ProgramData\GuardianNode"`
   - Manually clean up start-menu shortcuts.

## Performance

### Backend uses too much CPU during classification
This is the LLM doing its job. To reduce:
- Switch to a smaller model preset in **Settings → Model Status**
- Reduce OCR frequency in **Settings → Capture** (e.g. every 10s instead of 5s)
- Move backend to a separate PC (see [Move server to another PC](move-server-to-another-pc.md))

### Agent uses too much disk space
By default the agent keeps unflagged OCR cache for 24 hours and screenshots only for flagged events. If usage is still high:
- **Settings → Retention** → lower the alert retention periods
- **Settings → Storage** → click **Wipe screenshot evidence**

## Still stuck

Open an issue at https://github.com/the-vibe-dev/guardiannode/issues with:
- The wizard page or screen where you got stuck
- The contents of the log file at `C:\ProgramData\GuardianNode\logs\`, after
  removing personal information. Do not post child screenshots, private
  messages, pairing codes, or evidence exports in public issues.
- Your OS version, RAM, and the model size you picked

We'll get back to you.
