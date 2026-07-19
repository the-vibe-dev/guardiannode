; GuardianNode Server Installer (Windows)
; Installs the backend, dashboard, and Ollama on a parent server PC.

#define MyAppName "GuardianNode Server"
#define MyAppVersion "0.1.0-alpha.2"
#define MyAppPublisher "GuardianNode Contributors"
#define MyAppURL "https://github.com/the-vibe-dev/guardiannode"

[Setup]
AppId={{C7D8E9F0-1234-5678-9ABC-DEF012345678}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\GuardianNodeServer
DefaultGroupName=GuardianNode Server
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputBaseFilename=GuardianNodeServerSetup-{#MyAppVersion}
OutputDir=..\build\dist
Compression=lzma2/ultra
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\build\stage\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\stage\dashboard\*"; DestDir: "{app}\backend\app\static"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "..\build\stage\winsw\WinSW.exe"; DestDir: "{app}"; DestName: "GuardianNodeBackendService.exe"; Flags: ignoreversion
Source: "..\build\stage\winsw\Backend.xml"; DestDir: "{app}"; DestName: "GuardianNodeBackendService.xml"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\shared\configure_ollama_windows.ps1"; Flags: dontcopy
Source: "..\shared\configure_ollama_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "show_setup_token.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\GuardianNode"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\logs"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\keys"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\evidence"; Permissions: system-modify

[Icons]
Name: "{commonprograms}\GuardianNode Server\Open Dashboard"; Filename: "http://127.0.0.1:8787/setup"
Name: "{commonprograms}\GuardianNode Server\Show Setup Token"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\show_setup_token.ps1"""
Name: "{commonprograms}\GuardianNode Server\Stop service"; Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"
Name: "{commonprograms}\GuardianNode Server\Start service"; Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"

[Run]
; Write server.env before any service or model helper starts.
Filename: "cmd.exe"; Parameters: "/C exit /B 0"; Flags: runhidden waituntilterminated; StatusMsg: "Writing GuardianNode server configuration..."; BeforeInstall: WriteRuntimeConfigBeforeStart

; Restrict server data to the backend service account and administrators before startup.
Filename: "icacls.exe"; Parameters: """{commonappdata}\GuardianNode"" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F"; Flags: runhidden waituntilterminated
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""GuardianNode Backend (Private LAN)"" dir=in action=allow protocol=TCP localport=8787 profile=private"; Flags: runhidden waituntilterminated; Check: ShouldEnableLanAccess

; Install backend service
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing backend service..."; Check: ShouldInstallBackendService
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; AfterInstall: RequireBackendHealth

; Open setup wizard
Filename: "http://127.0.0.1:8787/setup"; Flags: shellexec postinstall skipifsilent; Description: "Open Setup Wizard"

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""GuardianNode Backend (Private LAN)"""; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/End /TN GuardianNodeOllama"; Flags: runhidden waituntilterminated
Filename: "schtasks.exe"; Parameters: "/Delete /TN GuardianNodeOllama /F"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated

[UninstallDelete]
; WinSW may create final wrapper logs while its uninstall command is exiting.
; Remove those runtime-created files after all uninstall commands complete.
Type: filesandordirs; Name: "{app}"

[Code]
#include "..\shared\server_env_windows.iss"
#include "..\shared\hardware_tiers.iss"
#include "..\shared\upgrade_helpers.iss"

var
  HardwareSummaryPage: TOutputMsgWizardPage;
  NetworkPage: TInputOptionWizardPage;
  LanAddressPage: TInputQueryWizardPage;
  DetectedTier: String;
  DetectedTextModel: String;
  DetectedVisionModel: String;
  DetectedReasoning: String;
  UpgradeInProgress: Boolean;
  WasExistingInstall: Boolean;
  PreUpgradeBackupDir: String;

procedure ExitProcess(ExitCode: Integer);
  external 'ExitProcess@kernel32.dll stdcall';
function GetCurrentProcessId: Integer;
  external 'GetCurrentProcessId@kernel32.dll stdcall';

function InstallerParam(Name: String): String;
begin
  Result := Trim(ExpandConstant('{param:' + Name + '|}'));
end;

function HasLanParam: Boolean;
var
  LanParam: String;
begin
  LanParam := Lowercase(InstallerParam('LAN'));
  Result := (LanParam = '1') or (LanParam = 'yes') or (LanParam = 'true') or
    (LanParam = 'private') or (LanParam = 'lan');
end;

function LanHostValue: String;
begin
  Result := Trim(InstallerParam('SERVERHOST'));
  if Result = '' then
    Result := Trim(InstallerParam('ALLOWEDHOSTS'));
  if (Result = '') and Assigned(LanAddressPage) then
    Result := Trim(LanAddressPage.Values[0]);
end;

function ShouldEnableLanAccess: Boolean;
begin
  Result := HasLanParam or (Assigned(NetworkPage) and (NetworkPage.SelectedValueIndex = 1));
end;

function EffectiveAllowedHosts: String;
var
  HostValue: String;
begin
  HostValue := LanHostValue;
  if HostValue = '' then
    HostValue := 'guardian-server';
  Result := '127.0.0.1,localhost,' + HostValue;
end;

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

procedure ProbeHardware;
var
  ResultCode, RamGB, VramGB: Integer;
  ScriptPath, TmpPath: String;
  Lines: TArrayOfString;
  Output: String;
begin
  DetectedTier := 'text_only';
  DetectedTextModel := '';
  DetectedVisionModel := '';
  DetectedReasoning := 'Hardware probe did not complete. Conservative default: rules/OCR only until the parent explicitly changes models.';

  TmpPath := ExpandConstant('{tmp}\hw_probe.txt');
  ScriptPath := ExpandConstant('{tmp}\gn_hw_probe.ps1');
  SaveStringToFile(ScriptPath, HardwareProbeScript(), False);
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" -OutPath "' + TmpPath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if LoadStringsFromFile(TmpPath, Lines) and (GetArrayLength(Lines) > 0) then begin
    Output := Lines[0];
    RamGB := 4; VramGB := 0;
    if Pos('ram_gb=', Output) > 0 then
      RamGB := StrToIntDef(Trim(Copy(Output, Pos('ram_gb=', Output)+7, Pos(' vram_gb=', Output) - (Pos('ram_gb=', Output)+7))), 4);
    if Pos('vram_gb=', Output) > 0 then
      VramGB := StrToIntDef(Trim(Copy(Output, Pos('vram_gb=', Output)+8, 99)), 0);

    if VramGB >= {#GN_FULL_MIN_VRAM_GB} then begin
      DetectedTier := 'full';
      DetectedTextModel := '{#GN_FULL_TEXT_MODEL}';
      DetectedVisionModel := '{#GN_VISION_MODEL}';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU — vision LLM + text LLM run together.';
    end else if VramGB >= {#GN_VISION_ONLY_MIN_VRAM_GB} then begin
      DetectedTier := 'vision_only';
      DetectedVisionModel := '{#GN_VISION_MODEL}';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU — vision LLM only.';
    end else if RamGB >= 8 then begin
      DetectedTier := 'text_only';
      DetectedTextModel := '{#GN_TEXT_ONLY_MODEL}';
      DetectedVisionModel := '';
      DetectedReasoning := 'No GPU — Tesseract + small text LLM on CPU. Visual-only risks won''t be detected.';
    end else begin
      DetectedTier := 'text_only';
      DetectedReasoning := 'Limited RAM. Rules engine only.';
    end;
  end;
end;

function GetTier(Param: String): String;        begin Result := DetectedTier;        end;
function GetTextModel(Param: String): String;   begin Result := DetectedTextModel;   end;
function GetVisionModel(Param: String): String; begin Result := DetectedVisionModel; end;

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

function IsExistingInstall: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonappdata}\GuardianNode\server.env')) or
    GNServiceExists('GuardianNodeBackend');
end;

function ShouldInstallBackendService: Boolean;
begin
  Result := not GNServiceExists('GuardianNodeBackend');
end;

procedure RunHidden(const ExeName, Params: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant(ExeName), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure DeinitializeSetup;
begin
  // Inno Setup restores replaced files on a failed install. Restart the
  // existing registration so the previous release comes back online.
  if UpgradeInProgress and GNServiceExists('GuardianNodeBackend') then begin
    RunHidden('{sys}\sc.exe', 'start GuardianNodeBackend');
    UpgradeInProgress := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  WasExistingInstall := IsExistingInstall;
  PreUpgradeBackupDir := '';
  ExtractTemporaryFile('configure_ollama_windows.ps1');
  if not RunOllamaSetup(ExpandConstant('{tmp}\configure_ollama_windows.ps1')) then begin
    Result := 'GuardianNode Ollama/model setup failed. Check C:\ProgramData\GuardianNode\logs\install-ollama.log.';
    Exit;
  end;

  if WasExistingInstall then begin
    UpgradeInProgress := True;
    RunHidden('{sys}\sc.exe', 'stop GuardianNodeBackend');
    if not GNCreatePreUpgradeBackup(
      ExpandConstant('{commonappdata}\GuardianNode'),
      ExpandConstant('{app}'),
      PreUpgradeBackupDir) then begin
      RunHidden('{sys}\sc.exe', 'start GuardianNodeBackend');
      UpgradeInProgress := False;
      Result := 'GuardianNode could not create a pre-upgrade database/key backup. The existing server was restarted.';
    end;
  end;
end;

procedure InitializeWizard;
begin
  ProbeHardware;

  HardwareSummaryPage := CreateOutputMsgPage(wpWelcome,
    'Hardware check',
    'Detected tier: ' + DetectedTier,
    DetectedReasoning + #13#10#13#10 +
    'Text model: ' + DetectedTextModel + #13#10 +
    'Vision model: ' + DetectedVisionModel + #13#10#13#10 +
    'Ollama and the right models will be installed automatically. This can take 5-20 minutes depending on download speed.');

  NetworkPage := CreateInputOptionPage(HardwareSummaryPage.ID,
    'Server access',
    'Where should this parent dashboard be reachable?',
    'Keep local-only for a one-PC install. Choose private LAN/VPN when this PC will be the parent server for child PCs.',
    True, False);
  NetworkPage.Add('Only this PC (safest default; dashboard opens at http://127.0.0.1:8787)');
  NetworkPage.Add('Private LAN/VPN child PCs can connect to this server');
  NetworkPage.SelectedValueIndex := 0;
  if HasLanParam then
    NetworkPage.SelectedValueIndex := 1;

  LanAddressPage := CreateInputQueryPage(NetworkPage.ID,
    'Private LAN/VPN address',
    'Enter the exact host or IP child PCs will use.',
    'Example: 192.168.1.42 or guardian-server.local. The installer opens TCP 8787 only for the Windows Private network profile.');
  LanAddressPage.Add('Server host/IP for child installers:', False);
  LanAddressPage.Values[0] := LanHostValue;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if IsExistingInstall and
     ((PageID = HardwareSummaryPage.ID) or (PageID = NetworkPage.ID) or
      (PageID = LanAddressPage.ID)) then begin
    Result := True;
    Exit;
  end;
  if (PageID = LanAddressPage.ID) and (not ShouldEnableLanAccess) then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if WizardSilent() then
    Exit;
  if (CurPageID = LanAddressPage.ID) and (LanHostValue = '') then begin
    MsgBox('Enter the server host/IP that child PCs will use, or go back and choose local-only.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure WriteRuntimeConfig;
var
  DataDir, BindHost, AllowedHosts: String;
begin
  DataDir := ExpandConstant('{commonappdata}\GuardianNode');
  if FileExists(AddBackslash(DataDir) + 'server.env') then
    Exit;
  BindHost := '127.0.0.1';
  AllowedHosts := '127.0.0.1,localhost';
  if ShouldEnableLanAccess then begin
    BindHost := '0.0.0.0';
    AllowedHosts := EffectiveAllowedHosts;
  end;

  WriteGuardianNodeServerEnvForNetwork(
    DataDir,
    DetectedTier,
    DetectedTextModel,
    DetectedVisionModel,
    'http://127.0.0.1:11434',
    BindHost,
    AllowedHosts
  );
end;

procedure WriteRuntimeConfigBeforeStart;
begin
  WriteRuntimeConfig;
end;

procedure ScheduleFreshInstallCleanup;
var
  CleanupPath, Script: String;
  ResultCode: Integer;
begin
  CleanupPath := ExpandConstant('{tmp}\guardiannode_failed_server_cleanup.ps1');
  Script :=
    'param([int]$SetupPid,[string]$AppDir,[string]$DataDir)' + #13#10 +
    'Wait-Process -Id $SetupPid -ErrorAction SilentlyContinue' + #13#10 +
    '$uninstaller = Join-Path $AppDir ''unins000.exe''' + #13#10 +
    'if (Test-Path $uninstaller) { Start-Process -FilePath $uninstaller -ArgumentList ''/VERYSILENT'',''/SUPPRESSMSGBOXES'',''/NORESTART'' -Wait }' + #13#10 +
    'Remove-Item -LiteralPath $DataDir -Recurse -Force -ErrorAction SilentlyContinue' + #13#10;
  SaveStringToFile(CleanupPath, Script, False);
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + CleanupPath + '" -SetupPid ' +
    IntToStr(GetCurrentProcessId) + ' -AppDir "' + ExpandConstant('{app}') +
    '" -DataDir "' + ExpandConstant('{commonappdata}\GuardianNode') + '"',
    '', SW_HIDE, ewNoWait, ResultCode);
end;

procedure FailAndRollbackBackendHealth;
var
  MarkerPath: String;
begin
  Log('Backend readiness gate failed; restoring the pre-install state.');
  RunHidden('{sys}\sc.exe', 'stop GuardianNodeBackend');
  if WasExistingInstall and (PreUpgradeBackupDir <> '') then begin
    if not GNRestorePreUpgradeBackup(
      PreUpgradeBackupDir,
      ExpandConstant('{commonappdata}\GuardianNode'),
      ExpandConstant('{app}')) then
      Log('ERROR: one or more pre-upgrade files could not be restored.');
    RunHidden('{sys}\sc.exe', 'start GuardianNodeBackend');
  end else begin
    RunHidden('{app}\GuardianNodeBackendService.exe', 'uninstall');
    ScheduleFreshInstallCleanup;
  end;
  MarkerPath := ExpandConstant('{commonappdata}\GuardianNode\logs\installer-health-failure.log');
  ForceDirectories(ExtractFileDir(MarkerPath));
  SaveStringToFile(MarkerPath, 'Backend readiness gate failed; installer rolled back.' + #13#10, False);
  ExitProcess(1);
end;

procedure RequireBackendHealth;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 ''http://127.0.0.1:8787/api/health/ready''; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 2 } while ((Get-Date) -lt $deadline); exit 1"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
    FailAndRollbackBackendHealth
  else
    UpgradeInProgress := False;
end;
