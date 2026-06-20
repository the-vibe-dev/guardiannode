; GuardianNode Server Installer (Windows)
; Installs the backend, dashboard, and Ollama on a parent server PC.

#define MyAppName "GuardianNode Server"
#define MyAppVersion "0.1.0-alpha.1"
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
Source: "..\shared\configure_ollama_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\GuardianNode"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\logs"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\keys"; Permissions: system-modify
Name: "{commonappdata}\GuardianNode\evidence"; Permissions: system-modify

[Icons]
Name: "{commonprograms}\GuardianNode Server\Open Dashboard"; Filename: "http://127.0.0.1:8787/setup"
Name: "{commonprograms}\GuardianNode Server\Show Setup Token"; Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""$p=Join-Path $env:ProgramData 'GuardianNode\keys\setup_token.json'; if(Test-Path $p){(Get-Content $p | ConvertFrom-Json).token | Write-Host; Read-Host 'Press Enter to close'} else {Write-Host 'Setup token file not found'; Read-Host 'Press Enter to close'}"""
Name: "{commonprograms}\GuardianNode Server\Stop service"; Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"
Name: "{commonprograms}\GuardianNode Server\Start service"; Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"

[Run]
; Install Ollama + pull models for detected tier (this is a SERVER install — always set up Ollama)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\configure_ollama_windows.ps1"" -Tier ""{code:GetTier}"" -TextModel ""{code:GetTextModel}"" -VisionModel ""{code:GetVisionModel}"" -OllamaUrl ""http://127.0.0.1:11434"""; Flags: runhidden waituntilterminated; StatusMsg: "Installing Ollama and pulling AI models (this may take 5-20 minutes)..."

; Install backend service
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing backend service..."
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated

; Open setup wizard
Filename: "http://127.0.0.1:8787/setup"; Flags: shellexec postinstall skipifsilent; Description: "Open Setup Wizard"

[UninstallRun]
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\GuardianNodeBackendService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated

[Code]
var
  HardwareSummaryPage: TOutputMsgWizardPage;
  DetectedTier: String;
  DetectedTextModel: String;
  DetectedVisionModel: String;
  DetectedReasoning: String;

procedure ProbeHardware;
var
  ResultCode, RamGB, VramGB: Integer;
  TmpPath: String;
  Lines: TArrayOfString;
  Output: String;
begin
  DetectedTier := 'vision_only';
  DetectedTextModel := '';
  DetectedVisionModel := 'qwen3-vl:8b-instruct';
  DetectedReasoning := 'Default tier; adjust later in dashboard.';

  TmpPath := ExpandConstant('{tmp}\hw_probe.txt');
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "$ram = [int]([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)); $vram = 0; try { $smi = Get-Command nvidia-smi -ErrorAction Stop; $line = & $smi --query-gpu=memory.total --format=csv,noheader,nounits | Select -First 1; if ($line) { $vram = [int]([math]::Floor([int]$line / 1024)) } } catch {}; ""ram_gb=$ram vram_gb=$vram"" | Out-File -Encoding ascii ''' + TmpPath + '''"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if LoadStringsFromFile(TmpPath, Lines) and (GetArrayLength(Lines) > 0) then begin
    Output := Lines[0];
    RamGB := 4; VramGB := 0;
    if Pos('ram_gb=', Output) > 0 then
      RamGB := StrToIntDef(Trim(Copy(Output, Pos('ram_gb=', Output)+7, Pos(' vram_gb=', Output) - (Pos('ram_gb=', Output)+7))), 4);
    if Pos('vram_gb=', Output) > 0 then
      VramGB := StrToIntDef(Trim(Copy(Output, Pos('vram_gb=', Output)+8, 99)), 0);

    if VramGB >= 16 then begin
      DetectedTier := 'full';
      DetectedTextModel := 'llama3.2:3b';
      DetectedVisionModel := 'qwen3-vl:8b-instruct';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU — vision LLM + text LLM run together.';
    end else if VramGB >= 6 then begin
      DetectedTier := 'vision_only';
      DetectedVisionModel := 'qwen3-vl:8b-instruct';
      DetectedReasoning := IntToStr(VramGB) + ' GB GPU — vision LLM only.';
    end else if RamGB >= 8 then begin
      DetectedTier := 'text_only';
      DetectedTextModel := 'llama3.2:1b';
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
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  CfgPath: String;
  CfgFile: TArrayOfString;
begin
  if CurStep = ssPostInstall then begin
    CfgPath := ExpandConstant('{commonappdata}\GuardianNode\server.env');
    SetArrayLength(CfgFile, 8);
    CfgFile[0] := 'GUARDIANNODE_BIND_HOST=127.0.0.1';
    CfgFile[1] := 'GUARDIANNODE_BIND_PORT=8787';
    CfgFile[2] := 'GUARDIANNODE_DATA_DIR=' + ExpandConstant('{commonappdata}\GuardianNode');
    CfgFile[3] := 'GUARDIANNODE_MDNS_ENABLED=false';
    CfgFile[4] := 'GUARDIANNODE_CLASSIFIER_TIER=' + DetectedTier;
    CfgFile[5] := 'GUARDIANNODE_TEXT_MODEL=' + DetectedTextModel;
    CfgFile[6] := 'GUARDIANNODE_VISION_MODEL=' + DetectedVisionModel;
    CfgFile[7] := 'GUARDIANNODE_OLLAMA_URL=http://127.0.0.1:11434';
    SaveStringsToFile(CfgPath, CfgFile, False);
  end;
end;
