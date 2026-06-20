; GuardianNode Child Device Installer
; Inno Setup 6.x

#define MyAppName "GuardianNode"
#define MyAppVersion "0.1.0-alpha.1"
#define MyAppPublisher "GuardianNode Contributors"
#define MyAppURL "https://github.com/the-vibe-dev/guardiannode"
#define MyAppExeName "GuardianNodeAgent.exe"

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
UninstallDisplayIcon={app}\{#MyAppExeName}
; Replace standard uninstall entry with our password-gated wrapper
UninstallFilesDir={app}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; ---- Bundled agent payload (PyInstaller one-folder output expected here) ----
Source: "..\build\stage\agent\*"; DestDir: "{app}\agent"; Flags: recursesubdirs createallsubdirs ignoreversion

; ---- Bundled backend (if all-in-one mode) ----
Source: "..\build\stage\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist

; ---- Dashboard built static files ----
Source: "..\build\stage\dashboard\*"; DestDir: "{app}\backend\app\static"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist

; ---- Custom uninstaller wrapper ----
Source: "..\build\stage\agent\GuardianNodeUninstall.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; ---- Documentation ----
Source: "..\..\PRIVACY.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md";   DestDir: "{app}"; Flags: ignoreversion

; ---- WinSW service wrapper (downloaded during build into stage/) ----
; The agent itself is NOT a service: services live in session 0 and cannot
; capture a logged-in user's desktop. The agent runs per user session via the
; GuardianNodeAgent scheduled task (see register_agent_task.ps1). Only the
; watchdog (tamper resistance) and the backend (all-in-one) are services.
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeWatchdogService.exe"; Flags: ignoreversion
Source: "..\build\stage\winsw\Watchdog.xml";    DestDir: "{app}"; DestName: "GuardianNodeWatchdogService.xml"; Flags: ignoreversion
; Secondary watchdog (mutual resurrection — see Helper.xml). GuardianNode-branded
; on purpose: transparent naming is a product requirement; tamper resistance
; comes from the service ACL (admin-only stop), not from hiding the name.
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeWatchdog2Service.exe"; Flags: ignoreversion
Source: "..\build\stage\winsw\Helper.xml";      DestDir: "{app}"; DestName: "GuardianNodeWatchdog2Service.xml"; Flags: ignoreversion
; Backend service only exists in all-in-one mode
Source: "..\build\stage\winsw\WinSW.exe";       DestDir: "{app}"; DestName: "GuardianNodeBackendService.exe"; Flags: ignoreversion; Check: IsAllInOne
Source: "..\build\stage\winsw\Backend.xml";     DestDir: "{app}"; DestName: "GuardianNodeBackendService.xml"; Flags: ignoreversion skipifsourcedoesntexist; Check: IsAllInOne

; ---- Scheduled-task registration helper ----
Source: "register_agent_task.ps1"; DestDir: "{app}"; Flags: ignoreversion

; ---- Brand icons (shortcuts + tray runtime icon) ----
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.png"; DestDir: "{app}\agent"; Flags: ignoreversion

; ---- Ollama / model bootstrap helper (used in all-in-one mode) ----
Source: "..\shared\configure_ollama_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion

; ---- Taskbar pin helper ----
Source: "pin_to_taskbar.ps1"; DestDir: "{app}"; Flags: ignoreversion

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

[Icons]
; Neither the agent nor the tray uses a Startup-folder shortcut — both run via
; scheduled tasks (logon trigger, all users) that the watchdog can re-run if
; killed. A Startup shortcut can be toggled off from Task Manager's Startup tab.
Name: "{commonprograms}\{#MyAppName}\GuardianNode Tray"; Filename: "{app}\agent\GuardianNodeTray.exe"; IconFilename: "{app}\icon.ico"
Name: "{commonprograms}\{#MyAppName}\Open Dashboard"; Filename: "{code:GetDashboardUrl}"; IconFilename: "{app}\icon.ico"
Name: "{commonprograms}\{#MyAppName}\Uninstall GuardianNode"; Filename: "{app}\GuardianNodeUninstall.exe"; Parameters: """{uninstallexe}"""; IconFilename: "{app}\icon.ico"

[Run]
; ---- Restrict install dir ACL (before anything starts) ----
Filename: "icacls.exe"; Parameters: """{app}"" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F /grant:r Users:(OI)(CI)RX"; Flags: runhidden waituntilterminated

; ---- All-in-one mode: install Ollama + pull models for the detected tier ----
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\configure_ollama_windows.ps1"" -Tier ""{code:GetTier}"" -TextModel ""{code:GetTextModel}"" -VisionModel ""{code:GetVisionModel}"" -OllamaUrl ""http://127.0.0.1:11434"""; Flags: runhidden waituntilterminated; StatusMsg: "Installing Ollama and pulling AI models (this may take 5-20 minutes)..."; Check: IsAllInOne

; ---- All-in-one mode: install + start the backend service first so the agent can pair against it ----
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing GuardianNode Backend service..."; Check: IsAllInOne
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; Check: IsAllInOne

; ---- Clean up the agent service from older installs (the agent is a scheduled
; task now — a session-0 service cannot capture the desktop and caused duplicate
; capture instances). Best-effort: errors are ignored on fresh machines.
Filename: "sc.exe"; Parameters: "stop GuardianNodeAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete GuardianNodeAgent"; Flags: runhidden waituntilterminated

; ---- Register the agent + tray as logon scheduled tasks for ALL users and start them ----
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_agent_task.ps1"" -AgentExe ""{app}\agent\GuardianNodeAgent.exe"" -TaskName ""GuardianNodeAgent"""; Flags: runhidden waituntilterminated; StatusMsg: "Registering GuardianNode monitoring for all users..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_agent_task.ps1"" -AgentExe ""{app}\agent\GuardianNodeTray.exe"" -TaskName ""GuardianNodeTray"""; Flags: runhidden waituntilterminated; StatusMsg: "Registering GuardianNode tray for all users..."

; ---- Install + start BOTH watchdog services (each revives the other + the agent/tray tasks) ----
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing GuardianNode Watchdog service..."
Filename: "{app}\GuardianNodeWatchdogService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeWatchdog2Service.exe"; Parameters: "install"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeWatchdog2Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated

; ---- Restrict the service ACLs: deny stop/delete to non-admin ----
Filename: "sc.exe"; Parameters: "sdset GuardianNodeWatchdog D:(D;;DCLCWPDTSD;;;IU)(D;;DCLCWPDTSD;;;SU)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "sdset GuardianNodeWatchdog2 D:(D;;DCLCWPDTSD;;;IU)(D;;DCLCWPDTSD;;;SU)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"; Flags: runhidden waituntilterminated

; ---- Remove the legacy obscurely-named secondary watchdog from older installs ----
Filename: "sc.exe"; Parameters: "stop EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete EndpointHealthAgent"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "sdset GuardianNodeBackend D:(D;;DCLCWPDTSD;;;IU)(D;;DCLCWPDTSD;;;SU)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"; Flags: runhidden waituntilterminated; Check: IsAllInOne

; ---- Start the tray now for the installing user (per-session mutex prevents duplicates) ----
Filename: "{app}\agent\GuardianNodeTray.exe"; Flags: nowait runasoriginaluser

; ---- Pin Tray to the parent user's taskbar. Pin the Start Menu shortcut (it
; carries the brand icon), not the bare exe. ----
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\pin_to_taskbar.ps1"" -Target ""{commonprograms}\{#MyAppName}\GuardianNode Tray.lnk"""; Flags: runhidden waituntilterminated runasoriginaluser skipifsilent; StatusMsg: "Pinning GuardianNode to the taskbar..."

; ---- Launch dashboard at the end (first-run web setup creates the parent account + recovery code) ----
; Child-only installs with auto-discovery have no known dashboard URL — there is
; no local backend, so opening http://127.0.0.1:8787 would be wrong. In that case
; the checkbox is skipped and the finish page tells the parent to manage the
; device from the parent computer (see UpdateReadyMemo/CurPageChanged below).
Filename: "{code:GetDashboardUrl}"; Flags: shellexec postinstall skipifsilent; Description: "Open Parent Dashboard to finish setup"; Check: ShouldOpenDashboard

[UninstallRun]
; Both watchdogs first, or they would revive each other / the tasks mid-uninstall.
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
Filename: "taskkill.exe"; Parameters: "/IM GuardianNodeAgent.exe /F"; Flags: runhidden waituntilterminated
Filename: "taskkill.exe"; Parameters: "/IM GuardianNodeTray.exe /F"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
var
  ModePage: TInputOptionWizardPage;
  ChildProfilePage: TInputOptionWizardPage;
  ServerConnectionPage: TInputQueryWizardPage;
  HardwareSummaryPage: TOutputMsgWizardPage;
  // Hardware-probe result, filled in during ProbeHardware()
  DetectedTier: String;     // full / vision_only / text_only
  DetectedTextModel: String;
  DetectedVisionModel: String;
  DetectedReasoning: String;

// Detect classifier tier by running PowerShell. We can't run the full
// hardware_probe.py at install time (Python isn't there yet), so we do a
// minimal inline detection: count RAM and check for nvidia-smi VRAM.
procedure ProbeHardware;
var
  ResultCode: Integer;
  TmpPath: String;
  Lines: TArrayOfString;
  Output: String;
  RamGB, VramGB: Integer;
begin
  DetectedTier := 'vision_only';
  DetectedTextModel := '';
  DetectedVisionModel := 'qwen3-vl:8b-instruct';
  DetectedReasoning := 'Default tier; adjust later in dashboard.';

  TmpPath := ExpandConstant('{tmp}\hw_probe.txt');
  // PowerShell inline: emit "ram_gb=X vram_gb=Y" with VRAM 0 if no nvidia-smi.
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "$ram = [int]([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)); $vram = 0; try { $smi = Get-Command nvidia-smi -ErrorAction Stop; $line = & $smi --query-gpu=memory.total --format=csv,noheader,nounits | Select -First 1; if ($line) { $vram = [int]([math]::Floor([int]$line / 1024)) } } catch {}; ""ram_gb=$ram vram_gb=$vram"" | Out-File -Encoding ascii ''' + TmpPath + '''"',
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

    // NOTE: a single 12 GB GPU does NOT fit the "full" tier — qwen2.5vl alone
    // wants ~11 GB once its compute graph is allocated, so adding a second
    // (text) model thrashes VRAM and the vision model errors out. vision_only
    // already does OCR + image + text classification, so we only pick "full"
    // at 16 GB+ where both models genuinely fit hot.
    if VramGB >= 16 then begin
      DetectedTier := 'full';
      DetectedTextModel := 'llama3.2:3b';
      DetectedVisionModel := 'qwen3-vl:8b-instruct';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU detected — vision LLM plus a separate text LLM run together for a second opinion on extracted text.';
    end else if VramGB >= 6 then begin
      DetectedTier := 'vision_only';
      DetectedTextModel := '';
      DetectedVisionModel := 'qwen3-vl:8b-instruct';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU detected — the vision model detects visual risks (nudity, gore, weapons, etc.), reads the on-screen text, and classifies it (grooming, self-harm, scams) in one pass. Full coverage.';
    end else if RamGB >= 8 then begin
      DetectedTier := 'text_only';
      DetectedTextModel := 'llama3.2:1b';
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
begin
  Result := (ModePage.SelectedValueIndex = 0);
end;

procedure RunHidden(const ExeName, Params: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant(ExeName), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  // Free locked binaries before the file-copy stage so upgrades don't roll back
  // with "file in use". Stop BOTH watchdogs first (they revive each other), then
  // the legacy agent service, the scheduled tasks, and finally the processes.
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeWatchdog2');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeWatchdog2');
  RunHidden('{sys}\sc.exe', 'stop EndpointHealthAgent');   // legacy name (pre-rename installs)
  RunHidden('{sys}\sc.exe', 'delete EndpointHealthAgent');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeWatchdog');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeWatchdog');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeAgent');
  RunHidden('{sys}\sc.exe', 'delete GuardianNodeAgent');
  RunHidden('{sys}\schtasks.exe', '/End /TN GuardianNodeAgent');
  RunHidden('{sys}\schtasks.exe', '/End /TN GuardianNodeTray');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeWatchdog.exe /F');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeAgent.exe /F');
  RunHidden('{sys}\taskkill.exe', '/IM GuardianNodeTray.exe /F');
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

function InstallerParam(Name: String): String;
begin
  Result := Trim(ExpandConstant('{param:' + Name + '|}'));
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

function AgeGroupValue: String;
begin
  case ChildProfilePage.SelectedValueIndex of
    0: Result := 'under_10';
    1: Result := '10_13';
    2: Result := '14_17';
  else
    Result := '10_13';
  end;
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
  if (ModeParam = 'separated') or (ModeParam = 'child') or
     (ServerUrlParam <> '') or (PairCodeParam <> '') then
    ModePage.SelectedValueIndex := 1;

  // -- Child profile --
  ChildProfilePage := CreateInputOptionPage(ModePage.ID,
    'Child profile',
    'How old is the child using this PC?',
    'GuardianNode adjusts detection sensitivity by age group. You''ll create your parent account and password in the dashboard right after installation.',
    True, False);
  ChildProfilePage.Add('Under 10');
  ChildProfilePage.Add('10 – 13');
  ChildProfilePage.Add('14 – 17');
  ChildProfilePage.SelectedValueIndex := 1;

  // -- Server connection (only used in separated mode) --
  ServerConnectionPage := CreateInputQueryPage(ChildProfilePage.ID,
    'Connect to GuardianNode server',
    'Enter the pairing code shown on your parent dashboard (Devices > Add device).',
    'Leave the server URL blank to search your home network automatically.');
  ServerConnectionPage.Add('Server URL (e.g. http://192.168.1.42:8787, or blank to auto-discover):', False);
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
  url: String;
begin
  Result := True;
  // Skip validation entirely in silent / very-silent install (CI, PoC, scripted).
  // Config will be written from environment defaults; the parent can complete
  // pairing + account setup via the dashboard's first-run wizard.
  if WizardSilent() then Exit;

  if CurPageID = ServerConnectionPage.ID then begin
    url := Trim(ServerConnectionPage.Values[0]);
    if (url <> '') and (Pos('http', url) <> 1) then begin
      MsgBox('Server URL must start with http:// (or leave it blank to auto-discover).', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Length(Trim(ServerConnectionPage.Values[1])) <> 6 then begin
      MsgBox('Pairing code must be 6 digits. Find it on the parent dashboard under Devices > Add device.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  CfgPath, PairPath, ServerUrl: String;
  CfgFile, PairFile: TArrayOfString;
begin
  if CurStep = ssPostInstall then begin
    ServerUrl := Trim(ServerConnectionPage.Values[0]);

    // Write the agent config based on wizard inputs
    CfgPath := ExpandConstant('{commonappdata}\GuardianNode\agent.yaml');
    SetArrayLength(CfgFile, 9);
    if IsAllInOne or (ServerUrl = '') then
      CfgFile[0] := 'backend_url: http://127.0.0.1:8787'
    else
      CfgFile[0] := 'backend_url: ' + ServerUrl;
    CfgFile[1] := 'age_group: ' + AgeGroupValue;
    CfgFile[2] := 'ocr_engine: tesseract';
    CfgFile[3] := 'ocr_cadence_seconds: 5';
    CfgFile[4] := 'ocr_min_confidence: 0.5';
    CfgFile[5] := 'phash_threshold: 2';
    CfgFile[6] := 'log_level: INFO';
    CfgFile[7] := 'dry_run: false';
    CfgFile[8] := 'full_screen_capture_enabled: true';
    SaveStringsToFile(CfgPath, CfgFile, False);

    // Drop the pending pairing handshake for the agent to complete on first
    // start. All-in-one uses the loopback-only bootstrap (no code needed);
    // separated mode uses the parent-issued 6-digit code. The agent deletes
    // this file once pairing succeeds.
    PairPath := ExpandConstant('{commonappdata}\GuardianNode\pending_pairing.json');
    SetArrayLength(PairFile, 1);
    if IsAllInOne then
      PairFile[0] := '{"backend_url": "http://127.0.0.1:8787", "local_bootstrap": true}'
    else
      PairFile[0] := '{"backend_url": "' + ServerUrl + '", "code": "' +
        Trim(ServerConnectionPage.Values[1]) + '"}';
    SaveStringsToFile(PairPath, PairFile, False);
  end;
end;
