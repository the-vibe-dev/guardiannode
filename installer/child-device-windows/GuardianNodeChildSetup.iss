; GuardianNode Child Device Installer
; Inno Setup 6.x

#define MyAppName "GuardianNode"
#define MyAppVersion "0.1.0-alpha.1"
#define MyAppPublisher "GuardianNode Contributors"
#define MyAppURL "https://github.com/the-vibe-dev/guardiannode"
#define MyAppExeName "GuardianNodeAgent.exe"
#define GuardianNodeServiceSddl "D:(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"

[Setup]
AppId={{6FB7AAA2-4F7E-4E1F-AA00-3F6C45B9B501}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputBaseFilename=GuardianNodeChildSetup-{#MyAppVersion}
OutputDir=..\build\dist
SetupIconFile=assets\icon.ico
SolidCompression=yes
Compression=lzma2/ultra
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableWelcomePage=no
UninstallDisplayIcon={app}\agent\{#MyAppExeName}
UninstallFilesDir={app}
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; ---- Bundled agent payload (PyInstaller one-folder output expected here) ----
Source: "..\build\stage\agent\*"; DestDir: "{app}\agent"; Flags: recursesubdirs createallsubdirs ignoreversion

; ---- Bundled backend (if all-in-one mode) ----
Source: "..\build\stage\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist; Check: IsAllInOne

; ---- Documentation ----
Source: "..\..\PRIVACY.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md";   DestDir: "{app}"; Flags: ignoreversion

; ---- WinSW service wrapper (downloaded during build into stage/) ----
; The agent itself is NOT a service: services live in session 0 and cannot
; capture a logged-in user's desktop. The agent runs per user session via the
; GuardianNodeAgent scheduled task (see register_agent_task.ps1). Only the
; endpoint broker, watchdog, and optional backend are services.
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeBrokerService.exe"; Flags: ignoreversion
Source: "..\build\stage\winsw\Broker.xml";      DestDir: "{app}"; DestName: "GuardianNodeBrokerService.xml"; Flags: ignoreversion
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeWatchdogService.exe"; Flags: ignoreversion
Source: "..\build\stage\winsw\Watchdog.xml";    DestDir: "{app}"; DestName: "GuardianNodeWatchdogService.xml"; Flags: ignoreversion
; Backend service only exists in all-in-one mode
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeBackendService.exe"; Flags: ignoreversion; Check: IsAllInOne
Source: "..\build\stage\winsw\Backend.xml";     DestDir: "{app}"; DestName: "GuardianNodeBackendService.xml"; Flags: ignoreversion skipifsourcedoesntexist; Check: IsAllInOne

; ---- Scheduled-task registration helper ----
Source: "register_agent_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "qualify_acls.ps1"; DestDir: "{app}"; Flags: ignoreversion

; ---- Brand icons (shortcuts + tray runtime icon) ----
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.png"; DestDir: "{app}\agent"; Flags: ignoreversion

; ---- Ollama / model bootstrap helper (used in all-in-one mode) ----
Source: "..\shared\configure_ollama_windows.ps1"; Flags: dontcopy
Source: "..\shared\configure_ollama_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Stale launchers from pre-scheduled-task installs (the mutex would collapse
; them anyway, but don't leave dead shortcuts around).
Type: files; Name: "{commonstartup}\GuardianNode Agent.lnk"
Type: files; Name: "{commonstartup}\GuardianNode Tray.lnk"

[Dirs]
Name: "{commonappdata}\GuardianNode"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\logs";  Permissions: system-modify
Name: "{commonappdata}\GuardianNode\keys";  Permissions: system-modify
Name: "{commonappdata}\GuardianNode\evidence"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\Secure"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\AgentSecure"; Permissions: system-modify

[Icons]
; Neither the agent nor the tray uses a Startup-folder shortcut — both run via
; scheduled tasks (logon trigger, all users) that the watchdog can re-run if
; killed. A Startup shortcut can be toggled off from Task Manager's Startup tab.
Name: "{commonprograms}\{#MyAppName}\GuardianNode Tray"; Filename: "{app}\agent\GuardianNodeTray.exe"; IconFilename: "{app}\icon.ico"
Name: "{commonprograms}\{#MyAppName}\Open Dashboard"; Filename: "{code:GetDashboardUrl}"; IconFilename: "{app}\icon.ico"

[Run]
; ---- Write runtime configuration before any service/task is allowed to start ----
Filename: "cmd.exe"; Parameters: "/C exit /B 0"; Flags: runhidden waituntilterminated; StatusMsg: "Writing GuardianNode configuration..."; BeforeInstall: WriteRuntimeConfigBeforeStart

; ---- Restrict install dir ACL (before anything starts) ----
Filename: "icacls.exe"; Parameters: """{app}"" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F /grant:r Users:(OI)(CI)RX"; Flags: runhidden waituntilterminated
Filename: "cmd.exe"; Parameters: "/C exit /B 0"; Flags: runhidden waituntilterminated; StatusMsg: "Securing GuardianNode data directories..."; BeforeInstall: HardenDataAclsBeforeStart

; ---- All-in-one mode: install + start the backend service first so the agent can pair against it ----
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing GuardianNode Backend service..."; Check: IsAllInOne
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; Check: IsAllInOne; AfterInstall: RequireBackendHealth

; ---- Clean up the agent service from older installs (the agent is a scheduled
; task now — a session-0 service cannot capture the desktop and caused duplicate
; capture instances). Best-effort: errors are ignored on fresh machines.
Filename: "sc.exe"; Parameters: "stop GuardianNodeAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete GuardianNodeAgent"; Flags: runhidden waituntilterminated

; ---- Install + start endpoint broker before session tasks. The broker owns
; device credentials, durable queue, pause state, and backend upload transport. ----
Filename: "{app}\agent\GuardianNodeBroker.exe"; Parameters: "--self-test"; Flags: runhidden waituntilterminated; StatusMsg: "Validating GuardianNode broker..."
Filename: "{app}\GuardianNodeBrokerService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing GuardianNode Endpoint Broker service..."
Filename: "sc.exe"; Parameters: "sdset GuardianNodeBroker {#GuardianNodeServiceSddl}"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBrokerService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; StatusMsg: "Starting GuardianNode Endpoint Broker service..."

; ---- Register the agent + tray as logon scheduled tasks for ALL users and start them ----
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_agent_task.ps1"" -AgentExe ""{app}\agent\GuardianNodeAgent.exe"" -TaskName ""GuardianNodeAgent"""; Flags: runhidden waituntilterminated; StatusMsg: "Registering GuardianNode monitoring for all users..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_agent_task.ps1"" -AgentExe ""{app}\agent\GuardianNodeTray.exe"" -TaskName ""GuardianNodeTray"""; Flags: runhidden waituntilterminated; StatusMsg: "Registering GuardianNode tray for all users..."

; ---- Install + start one watchdog service. WinSW/SCM recovery restarts the
; watchdog itself; the watchdog keeps the agent/tray scheduled tasks healthy. ----
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing GuardianNode Watchdog service..."
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated

; ---- Restrict the service ACLs: allow-only DACL, no explicit deny ACEs ----
Filename: "sc.exe"; Parameters: "sdset GuardianNodeWatchdog {#GuardianNodeServiceSddl}"; Flags: runhidden waituntilterminated

; ---- Remove legacy watchdog services from older installs ----
Filename: "sc.exe"; Parameters: "stop GuardianNodeWatchdog2"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete GuardianNodeWatchdog2"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "stop EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "sdset GuardianNodeBackend {#GuardianNodeServiceSddl}"; Flags: runhidden waituntilterminated; Check: IsAllInOne

; ---- Leave maintenance mode only after services/tasks are installed and started ----
Filename: "cmd.exe"; Parameters: "/C exit /B 0"; Flags: runhidden waituntilterminated; BeforeInstall: ClearMaintenanceMarker

; ---- Launch dashboard at the end (first-run web setup creates the parent account + recovery code) ----
; Child-only installs without an explicit server URL have no known dashboard URL — there is
; no local backend, so opening http://127.0.0.1:8787 would be wrong. In that case
; the checkbox is skipped and the finish page tells the parent to manage the
; device from the parent computer (see UpdateReadyMemo/CurPageChanged below).
Filename: "{code:GetDashboardUrl}"; Flags: shellexec postinstall skipifsilent; Description: "Open Parent Dashboard to finish setup"; Check: ShouldOpenDashboard

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""New-Item -ItemType Directory -Force -Path '$env:ProgramData\GuardianNode\Secure' | Out-Null; New-Item -ItemType File -Force -Path '$env:ProgramData\GuardianNode\Secure\maintenance.flag' | Out-Null"""; Flags: runhidden waituntilterminated
; Stop legacy secondary watchdog first if present, then the current watchdog.
Filename: "{app}\GuardianNodeWatchdog2Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\GuardianNodeWatchdog2Service.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist
; Legacy name from older installs
Filename: "sc.exe"; Parameters: "stop EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/End /TN GuardianNodeAgent"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/Delete /TN GuardianNodeAgent /F"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/End /TN GuardianNodeTray"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/Delete /TN GuardianNodeTray /F"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/End /TN GuardianNodeOllama"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/Delete /TN GuardianNodeOllama /F"; Flags: runhidden waituntilterminated
Filename: "taskkill.exe"; Parameters: "/IM GuardianNodeAgent.exe /F"; Flags: runhidden waituntilterminated
Filename: "taskkill.exe"; Parameters: "/IM GuardianNodeTray.exe /F"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBrokerService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\GuardianNodeBrokerService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "taskkill.exe"; Parameters: "/IM GuardianNodeBroker.exe /F"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
#include "..\shared\server_env_windows.iss"
#include "..\shared\hardware_tiers.iss"

var
  ModePage: TInputOptionWizardPage;
  ServerConnectionPage: TInputQueryWizardPage;
  HardwareSummaryPage: TOutputMsgWizardPage;
  // Hardware-probe result, filled in during ProbeHardware()
  DetectedTier: String;     // full / vision_only / text_only
  DetectedTextModel: String;
  DetectedVisionModel: String;
  DetectedReasoning: String;

function HardwareProbeScript: String;
begin
  Result :=
    'param([string]$OutPath)' + #13#10 +
    '$ram = [int]([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB))' + #13#10 +
    '$vram = 0' + #13#10 +
    '$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue' + #13#10 +
    'if ($smi) {' + #13#10 +
    '  $line = & $smi.Source --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1' + #13#10 +
    '  if ($line) { $vram = [int]([math]::Floor([int]$line / 1024)) }' + #13#10 +
    '}' + #13#10 +
    'if ($vram -le 0) {' + #13#10 +
    '  $class = ''HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}''' + #13#10 +
    '  foreach ($key in Get-ChildItem $class -ErrorAction SilentlyContinue) {' + #13#10 +
    '    $p = Get-ItemProperty $key.PSPath -ErrorAction SilentlyContinue' + #13#10 +
    '    if ($p.DriverDesc -match ''NVIDIA'') {' + #13#10 +
    '      $bytes = 0' + #13#10 +
    '      $qw = $p.''HardwareInformation.qwMemorySize''' + #13#10 +
    '      $legacy = $p.''HardwareInformation.MemorySize''' + #13#10 +
    '      if ($qw) { $bytes = [int64]$qw } elseif ($legacy) { $bytes = [int64][uint32]$legacy }' + #13#10 +
    '      $candidate = [int]([math]::Floor($bytes / 1GB))' + #13#10 +
    '      if ($candidate -gt $vram) { $vram = $candidate }' + #13#10 +
    '    }' + #13#10 +
    '  }' + #13#10 +
    '}' + #13#10 +
    '"ram_gb=$ram vram_gb=$vram" | Out-File -Encoding ascii $OutPath' + #13#10;
end;

function InstallerParam(Name: String): String; forward;

// Detect classifier tier by running PowerShell. We can't run the full
// hardware_probe.py at install time (Python isn't there yet), so we do a
// minimal inline detection: count RAM and check nvidia-smi, then fall back to
// Windows display-adapter registry VRAM when NVML is unavailable.
procedure ProbeHardware;
var
  ResultCode: Integer;
  ScriptPath, TmpPath: String;
  Lines: TArrayOfString;
  Output: String;
  RamGB, VramGB: Integer;
begin
  DetectedTier := 'text_only';
  DetectedTextModel := '{#GN_TEXT_ONLY_MODEL}';
  DetectedVisionModel := '';
  DetectedReasoning := 'Hardware probe did not complete. Conservative default: Tesseract OCR plus a small CPU-capable text model.';

  TmpPath := ExpandConstant('{tmp}\hw_probe.txt');
  ScriptPath := ExpandConstant('{tmp}\gn_hw_probe.ps1');
  SaveStringToFile(ScriptPath, HardwareProbeScript(), False);
  // PowerShell emits "ram_gb=X vram_gb=Y" with VRAM 0 if no GPU source is usable.
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" -OutPath "' + TmpPath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if LoadStringsFromFile(TmpPath, Lines) and (GetArrayLength(Lines) > 0) then begin
    Output := Lines[0];
    RamGB := 0; VramGB := 0;
    // Crude parsing — Pascal doesn't have regex stdlib
    if Pos('ram_gb=', Output) > 0 then begin
      RamGB := StrToIntDef(Trim(Copy(Output, Pos('ram_gb=', Output)+7, Pos(' vram_gb=', Output) - (Pos('ram_gb=', Output)+7))), 4);
    end;
    if Pos('vram_gb=', Output) > 0 then begin
      VramGB := StrToIntDef(Trim(Copy(Output, Pos('vram_gb=', Output)+8, 99)), 0);
    end;

    if VramGB >= {#GN_FULL_MIN_VRAM_GB} then begin
      DetectedTier := 'full';
      DetectedTextModel := '{#GN_FULL_TEXT_MODEL}';
      DetectedVisionModel := '{#GN_VISION_MODEL}';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU detected — vision LLM plus a separate text LLM run together for a second opinion on extracted text.';
    end else if VramGB >= {#GN_VISION_ONLY_MIN_VRAM_GB} then begin
      DetectedTier := 'vision_only';
      DetectedTextModel := '';
      DetectedVisionModel := '{#GN_VISION_MODEL}';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU detected — the vision model detects visual risks (nudity, gore, weapons, etc.), reads the on-screen text, and classifies it (grooming, self-harm, scams) in one pass. Full coverage.';
    end else if RamGB >= 8 then begin
      DetectedTier := 'text_only';
      DetectedTextModel := '{#GN_TEXT_ONLY_MODEL}';
      DetectedVisionModel := '';
      DetectedReasoning := 'No suitable GPU detected. Lower-power path: Tesseract OCR + a small text LLM on the CPU. This reads and classifies on-screen TEXT only — visual-only risks (nudity/gore/weapons in images without captions) will NOT be detected. For full coverage, pair this PC with a GPU-enabled GuardianNode server.';
    end else begin
      DetectedTier := 'text_only';
      DetectedTextModel := '';
      DetectedReasoning := 'Limited RAM (' + IntToStr(RamGB) + ' GB). Rules engine only — no LLM nuance and no visual detection.';
    end;
  end;
end;

function IsAllInOne: Boolean;
var
  ModeParam: String;
begin
  ModeParam := Lowercase(InstallerParam('MODE'));
  if ModeParam = 'allinone' then begin
    Result := True;
    Exit;
  end;
  if (ModeParam = 'child') or (InstallerParam('SERVERURL') <> '') or
     (InstallerParam('PAIRCODE') <> '') then begin
    Result := False;
    Exit;
  end;
  Result := (ModePage.SelectedValueIndex = 0);
end;

procedure RunHidden(const ExeName, Params: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant(ExeName), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function MaintenanceMarkerPath: String;
begin
  Result := ExpandConstant('{commonappdata}\GuardianNode\Secure\maintenance.flag');
end;

procedure CreateMaintenanceMarker;
var
  Lines: TArrayOfString;
begin
  ForceDirectories(ExpandConstant('{commonappdata}\GuardianNode\Secure'));
  SetArrayLength(Lines, 1);
  Lines[0] := 'GuardianNode installer maintenance in progress.';
  SaveStringsAtomic(MaintenanceMarkerPath, Lines);
end;

procedure ClearMaintenanceMarker;
begin
  DeleteFile(MaintenanceMarkerPath);
end;

procedure RequireBackendHealth;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 ''http://127.0.0.1:8787/api/health''; if ($r.StatusCode -ge 200) { exit 0 } } catch {}; Start-Sleep -Seconds 2 } while ((Get-Date) -lt $deadline); exit 1"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
    RaiseException('GuardianNode backend did not become healthy after service start.');
end;

function ValidateInstallInputs(var ErrorMessage: String): Boolean; forward;
function RunOllamaSetup(ScriptPath: String): Boolean; forward;
function RunTesseractOnlySetup(ScriptPath: String): Boolean; forward;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ErrorMessage: String;
begin
  if not ValidateInstallInputs(ErrorMessage) then begin
    Result := ErrorMessage;
    Exit;
  end;

  CreateMaintenanceMarker;

  // Free locked binaries before the file-copy stage so upgrades don't roll back
  // with "file in use". Stop the legacy secondary watchdog first if present,
  // then the current watchdog, legacy agent service, scheduled tasks, and
  // finally the processes.
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeWatchdog2');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeWatchdog2');
  RunHidden('{sys}\sc.exe', 'stop EndpointHealthAgent');   // legacy name (pre-rename installs)
  RunHidden('{sys}\sc.exe', 'delete EndpointHealthAgent');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeWatchdog');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeWatchdog');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeAgent');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeAgent');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeBackend');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeBackend');
  RunHidden('{sys}\schtasks.exe', '/End /TN GuardianNodeAgent');
  RunHidden('{sys}\schtasks.exe', '/End /TN GuardianNodeTray');
  RunHidden('{sys}\schtasks.exe', '/End /TN GuardianNodeOllama');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeWatchdog.exe /F');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeAgent.exe /F');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeTray.exe /F');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeBroker');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeBroker');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeBroker.exe /F');
  ExtractTemporaryFile('configure_ollama_windows.ps1');
  if IsAllInOne then begin
    if not RunOllamaSetup(ExpandConstant('{tmp}\configure_ollama_windows.ps1')) then begin
      Result := 'GuardianNode Ollama/model setup failed. Check C:\ProgramData\GuardianNode\logs\install-ollama.log.';
      Exit;
    end;
  end else begin
    if not RunTesseractOnlySetup(ExpandConstant('{tmp}\configure_ollama_windows.ps1')) then begin
      Result := 'GuardianNode OCR setup failed. Check C:\ProgramData\GuardianNode\logs\install-ollama.log.';
      Exit;
    end;
  end;
  Result := '';
end;

function GetTier(Param: String): String;
begin
  Result := DetectedTier;
end;

function GetTextModel(Param: String): String;
begin
  Result := DetectedTextModel;
end;

function GetVisionModel(Param: String): String;
begin
  Result := DetectedVisionModel;
end;

function RunOllamaSetup(ScriptPath: String): Boolean;
var
  ResultCode: Integer;
  Params: String;
begin
  Params :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"' +
    ' -Tier "' + GetTier('') + '"' +
    ' -TextModel "' + GetTextModel('') + '"' +
    ' -VisionModel "' + GetVisionModel('') + '"' +
    ' -OllamaUrl "http://127.0.0.1:11434"';
  Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := ResultCode = 0;
end;

function RunTesseractOnlySetup(ScriptPath: String): Boolean;
var
  ResultCode: Integer;
  Params: String;
begin
  Params :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"' +
    ' -Tier "text_only"' +
    ' -TextModel ""' +
    ' -VisionModel ""' +
    ' -OllamaUrl "http://127.0.0.1:11434"' +
    ' -TesseractOnly';
  Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := ResultCode = 0;
end;

function InstallerParam(Name: String): String;
begin
  Result := Trim(ExpandConstant('{param:' + Name + '|}'));
end;

function HasOnlyAsciiDigits(Value: String; ExpectedLength: Integer): Boolean;
var
  I: Integer;
begin
  Result := Length(Value) = ExpectedLength;
  if not Result then
    Exit;
  for I := 1 to Length(Value) do begin
    if (Ord(Value[I]) < Ord('0')) or (Ord(Value[I]) > Ord('9')) then begin
      Result := False;
      Exit;
    end;
  end;
end;

function ContainsAny(Value, BadChars: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to Length(BadChars) do begin
    if Pos(Copy(BadChars, I, 1), Value) > 0 then begin
      Result := True;
      Exit;
    end;
  end;
end;

function IsValidHostname(Host: String): Boolean;
var
  I: Integer;
  Ch: Char;
begin
  Result := False;
  if Host = '' then
    Exit;
  if (Host[1] = '-') or (Host[Length(Host)] = '-') or
     (Host[1] = '.') or (Host[Length(Host)] = '.') then
    Exit;
  for I := 1 to Length(Host) do begin
    Ch := Host[I];
    if not (((Ch >= 'A') and (Ch <= 'Z')) or
            ((Ch >= 'a') and (Ch <= 'z')) or
            ((Ch >= '0') and (Ch <= '9')) or
            (Ch = '.') or (Ch = '-')) then
      Exit;
  end;
  Result := True;
end;

function IsValidIpv6Literal(Host: String): Boolean;
var
  I: Integer;
  Ch: Char;
begin
  Result := False;
  if (Host = '') or (Pos(':', Host) = 0) then
    Exit;
  for I := 1 to Length(Host) do begin
    Ch := Host[I];
    if not (((Ch >= 'A') and (Ch <= 'F')) or
            ((Ch >= 'a') and (Ch <= 'f')) or
            ((Ch >= '0') and (Ch <= '9')) or
            (Ch = ':') or (Ch = '.')) then
      Exit;
  end;
  Result := True;
end;

function IsValidPort(PortText: String): Boolean;
var
  Port: Integer;
begin
  Result := False;
  if not HasOnlyAsciiDigits(PortText, Length(PortText)) then
    Exit;
  Port := StrToIntDef(PortText, 0);
  Result := (Port >= 1) and (Port <= 65535);
end;

function IsValidServerUrl(Url: String): Boolean;
var
  Rest, Host, PortText: String;
  SlashPos, BracketPos, ColonPos: Integer;
begin
  Result := False;
  Url := Trim(Url);
  if Url = '' then
    Exit;
  if ContainsAny(Url, ' "'#9#10#13) or (Pos('@', Url) > 0) or
     (Pos('#', Url) > 0) or (Pos('?', Url) > 0) then
    Exit;
  if Copy(Lowercase(Url), 1, 7) = 'http://' then
    Rest := Copy(Url, 8, Length(Url))
  else if Copy(Lowercase(Url), 1, 8) = 'https://' then
    Rest := Copy(Url, 9, Length(Url))
  else
    Exit;

  SlashPos := Pos('/', Rest);
  if SlashPos > 0 then begin
    if SlashPos <> Length(Rest) then
      Exit;
    Rest := Copy(Rest, 1, SlashPos - 1);
  end;
  if Rest = '' then
    Exit;

  if Rest[1] = '[' then begin
    BracketPos := Pos(']', Rest);
    if BracketPos <= 2 then
      Exit;
    Host := Copy(Rest, 2, BracketPos - 2);
    if not IsValidIpv6Literal(Host) then
      Exit;
    if BracketPos < Length(Rest) then begin
      if Rest[BracketPos + 1] <> ':' then
        Exit;
      PortText := Copy(Rest, BracketPos + 2, Length(Rest));
      if not IsValidPort(PortText) then
        Exit;
    end;
  end else begin
    ColonPos := Pos(':', Rest);
    if ColonPos > 0 then begin
      Host := Copy(Rest, 1, ColonPos - 1);
      PortText := Copy(Rest, ColonPos + 1, Length(Rest));
      if not IsValidPort(PortText) then
        Exit;
    end else begin
      Host := Rest;
    end;
    if (Pos(':', Host) > 0) or (not IsValidHostname(Host)) then
      Exit;
  end;

  Result := True;
end;

function JsonEscape(Value: String): String;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to Length(Value) do begin
    if Value[I] = '\' then
      Result := Result + '\\'
    else if Value[I] = '"' then
      Result := Result + '\"'
    else
      Result := Result + Value[I];
  end;
end;

function ValidateInstallInputs(var ErrorMessage: String): Boolean;
var
  Mode, ServerUrl, PairCode: String;
begin
  Result := False;
  ErrorMessage := '';
  Mode := Lowercase(InstallerParam('MODE'));
  ServerUrl := Trim(ServerConnectionPage.Values[0]);
  PairCode := Trim(ServerConnectionPage.Values[1]);

  if Mode = '' then begin
    if WizardSilent() then begin
      ErrorMessage := 'Silent install requires /MODE=allinone or /MODE=child.';
      Exit;
    end;
    if ModePage.SelectedValueIndex = 0 then
      Mode := 'allinone'
    else
      Mode := 'child';
  end;

  if (Mode <> 'allinone') and (Mode <> 'child') then begin
    if Mode = 'server' then
      ErrorMessage := 'Use GuardianNodeServerSetup for /MODE=server installs.'
    else
      ErrorMessage := 'Invalid /MODE. Use /MODE=allinone or /MODE=child.';
    Exit;
  end;

  if Mode = 'child' then begin
    if ServerUrl = '' then begin
      ErrorMessage := 'Child mode requires /SERVERURL with the trusted LAN/VPN GuardianNode server URL.';
      Exit;
    end;
    if not IsValidServerUrl(ServerUrl) then begin
      ErrorMessage := 'Server URL must be http:// or https:// with a valid host, optional port, no credentials, and no fragment/query.';
      Exit;
    end;
    if not HasOnlyAsciiDigits(PairCode, 6) then begin
      ErrorMessage := 'Pairing code must be exactly six ASCII digits.';
      Exit;
    end;
  end else begin
    if (ServerUrl <> '') or (PairCode <> '') then begin
      ErrorMessage := '/SERVERURL and /PAIRCODE are only valid with /MODE=child.';
      Exit;
    end;
  end;

  Result := True;
end;

function GetDashboardUrl(Param: String): String;
begin
  if IsAllInOne then
    Result := 'http://127.0.0.1:8787'
  else
    // Child-only: the dashboard lives on the parent server. Never fall back
    // to 127.0.0.1 here — there is no local backend on a child-only machine.
    Result := Trim(ServerConnectionPage.Values[0]);
end;

function ShouldOpenDashboard: Boolean;
begin
  // Open the dashboard only when we actually know where it is: all-in-one
  // (local backend) or child-only with an explicitly entered server URL.
  Result := IsAllInOne or (Trim(ServerConnectionPage.Values[0]) <> '');
end;

procedure InitializeWizard;
var
  ModeParam, ServerUrlParam, PairCodeParam: String;
begin
  ProbeHardware;
  ModeParam := Lowercase(InstallerParam('MODE'));
  ServerUrlParam := InstallerParam('SERVERURL');
  PairCodeParam := InstallerParam('PAIRCODE');

  // -- Mode selection --
  ModePage := CreateInputOptionPage(wpWelcome,
    'Choose installation mode',
    'How do you want to use GuardianNode on this PC?',
    'Pick the option that fits your family. You can change this later.',
    True, False);
  ModePage.Add('Install everything on this PC  (recommended for single-PC families)');
  ModePage.Add('This is the child''s PC — connect to an existing GuardianNode server');
  ModePage.SelectedValueIndex := 0;
  if (ModeParam = 'child') or (ServerUrlParam <> '') or (PairCodeParam <> '') then
    ModePage.SelectedValueIndex := 1;

  // -- Server connection (only used in separated mode) --
  ServerConnectionPage := CreateInputQueryPage(ModePage.ID,
    'Connect to GuardianNode server',
    'Enter the pairing code shown on your parent dashboard (Devices > Add device).',
    'Enter the exact server URL from the parent dashboard or setup guide.');
  ServerConnectionPage.Add('Server URL (e.g. http://192.168.1.42:8787):', False);
  ServerConnectionPage.Add('6-digit pairing code:', False);
  ServerConnectionPage.Values[0] := ServerUrlParam;
  ServerConnectionPage.Values[1] := PairCodeParam;

  // -- Hardware summary (only used in all-in-one mode) --
  HardwareSummaryPage := CreateOutputMsgPage(ServerConnectionPage.ID,
    'Hardware check',
    'Detected tier: ' + DetectedTier,
    DetectedReasoning + #13#10#13#10 +
    'Text model: ' + DetectedTextModel + #13#10 +
    'Vision model: ' + DetectedVisionModel);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = ServerConnectionPage.ID) and (ModePage.SelectedValueIndex = 0) then
    Result := True;
  if (PageID = HardwareSummaryPage.ID) and (ModePage.SelectedValueIndex = 1) then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorMessage: String;
begin
  Result := True;
  if WizardSilent() then Exit;

  if CurPageID = ServerConnectionPage.ID then begin
    if not ValidateInstallInputs(ErrorMessage) then begin
      MsgBox(ErrorMessage, mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure WriteRuntimeConfig;
var
  CfgPath, PairPath, ServerDataDir, ServerUrl: String;
  CfgFile, PairFile: TArrayOfString;
begin
  ServerUrl := Trim(ServerConnectionPage.Values[0]);
  ServerDataDir := ExpandConstant('{commonappdata}\GuardianNode');

  if IsAllInOne then
    WriteGuardianNodeServerEnv(
      ServerDataDir,
      DetectedTier,
      DetectedTextModel,
      DetectedVisionModel,
      'http://127.0.0.1:11434'
    );

  // Write the agent config based on wizard inputs
  CfgPath := AddBackslash(ServerDataDir) + 'agent.yaml';
  SetArrayLength(CfgFile, 8);
  if IsAllInOne or (ServerUrl = '') then
    CfgFile[0] := 'backend_url: http://127.0.0.1:8787'
  else
    CfgFile[0] := 'backend_url: ' + ServerUrl;
  CfgFile[1] := 'ocr_engine: tesseract';
  CfgFile[2] := 'ocr_cadence_seconds: 5';
  CfgFile[3] := 'ocr_min_confidence: 0.5';
  CfgFile[4] := 'phash_threshold: 2';
  CfgFile[5] := 'log_level: INFO';
  CfgFile[6] := 'dry_run: false';
  CfgFile[7] := 'full_screen_capture_enabled: true';
  SaveStringsAtomic(CfgPath, CfgFile);

  // Drop the pending pairing handshake for the agent to complete on first
  // start. All-in-one uses a loopback-only device bootstrap token generated
  // by the backend in keys\device_bootstrap_token.json; separated mode uses
  // the parent-issued 6-digit code. The agent deletes this file once pairing
  // succeeds.
  PairPath := ExpandConstant('{commonappdata}\GuardianNode\pending_pairing.json');
  SetArrayLength(PairFile, 1);
  if IsAllInOne then
    PairFile[0] := '{"backend_url": "http://127.0.0.1:8787", "local_bootstrap": true}'
  else
    PairFile[0] := '{"backend_url": "' + JsonEscape(ServerUrl) + '", "code": "' +
      JsonEscape(Trim(ServerConnectionPage.Values[1])) + '"}';
  SaveStringsAtomic(PairPath, PairFile);
end;

procedure WriteRuntimeConfigBeforeStart;
begin
  WriteRuntimeConfig;
end;

procedure HardenDataAclsBeforeStart;
var
  DataRoot: String;
begin
  DataRoot := ExpandConstant('{commonappdata}\GuardianNode');
  RunHidden('{sys}\icacls.exe', '"' + DataRoot + '\Secure" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F');
  RunHidden('{sys}\icacls.exe', '"' + DataRoot + '\AgentSecure" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F');
  RunHidden('{sys}\icacls.exe', '"' + DataRoot + '\keys" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F');
  RunHidden('{sys}\icacls.exe', '"' + DataRoot + '\server.env" /inheritance:r /grant:r SYSTEM:F /grant:r Administrators:F');
end;
