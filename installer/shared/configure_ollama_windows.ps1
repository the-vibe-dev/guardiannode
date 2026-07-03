# GuardianNode - Windows Ollama bootstrap.
#
# Called by the Inno Setup installer's [Run] section. Receives:
#   -Tier <full | vision_only | text_only>
#   -TextModel <ollama model tag, optional>
#   -VisionModel <ollama model tag, optional>
#   -OllamaUrl <http://host:port> (defaults to local)
#
# Behavior:
#   1. Check/install Tesseract OCR for deterministic phrase detection.
#   2. Check if Ollama is reachable. If not, download + silent-install Ollama for Windows.
#   3. Pull the required models for the chosen tier (skip if already pulled).
#   4. Configure service env: TESSDATA_PREFIX, PATH, OLLAMA_MAX_LOADED_MODELS, OLLAMA_KEEP_ALIVE.
#   5. Print final summary; exit 0 on success, non-zero on failure.

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("full","vision_only","text_only")]
    [string]$Tier,

    [string]$TextModel = "",
    [string]$VisionModel = "",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$LogPath = "C:\ProgramData\GuardianNode\logs\install-ollama.log",
    [switch]$TesseractOnly
)

$ErrorActionPreference = "Continue"

# Ensure log dir exists
$logDir = Split-Path $LogPath -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Write-Log {
    param([string]$Message)
    $line = "$([DateTime]::UtcNow.ToString('o')) $Message"
    Write-Host $line
    Add-Content -Path $LogPath -Value $line
}

# Pick default models per tier if not explicitly given. Child-only installs use
# Tesseract locally but send classification to the parent server.
if ($TesseractOnly) {
    $TextModel = ""
    $VisionModel = ""
} elseif (-not $TextModel) {
    switch ($Tier) {
        "full"        { $TextModel = "llama3.2:3b" }
        "text_only"   { $TextModel = "llama3.2:1b" }
        "vision_only" { $TextModel = "" }
    }
}
if (-not $VisionModel) {
    switch ($Tier) {
        "full"        { $VisionModel = "qwen3-vl:8b-instruct" }
        "vision_only" { $VisionModel = "qwen3-vl:8b-instruct" }
        "text_only"   { $VisionModel = "" }
    }
}

Write-Log "Tier: $Tier  TextModel: '$TextModel'  VisionModel: '$VisionModel'  OllamaUrl: $OllamaUrl"

function Test-OllamaReachable {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$OllamaUrl/api/tags" -TimeoutSec 5
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Download-File {
    param(
        [Parameter(Mandatory=$true)][string]$Url,
        [Parameter(Mandatory=$true)][string]$Destination
    )

    Remove-Item -Path $Destination -Force -ErrorAction SilentlyContinue
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        Write-Log "Downloading with curl.exe ..."
        & $curl.Source --fail --location --silent --show-error --connect-timeout 30 --max-time 1800 --retry 3 --retry-delay 5 --output $Destination $Url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $Destination) -and ((Get-Item $Destination).Length -gt 0)) {
            return $true
        }
        Write-Log "curl.exe download failed with exit code $LASTEXITCODE."
    }

    try {
        Write-Log "Downloading with Invoke-WebRequest ..."
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 1800
        return (Test-Path $Destination) -and ((Get-Item $Destination).Length -gt 0)
    } catch {
        Write-Log "Invoke-WebRequest download failed: $_"
        return $false
    }
}

function Get-TesseractExecutable {
    $tesseract = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($tesseract) {
        return $tesseract.Source
    }
    $candidates = @(
        (Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR\tesseract.exe")
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Set-TesseractEnvironment {
    param([Parameter(Mandatory=$true)][string]$TesseractExe)

    $installDir = Split-Path -Parent $TesseractExe
    $tessData = Join-Path $installDir "tessdata"
    [System.Environment]::SetEnvironmentVariable("TESSDATA_PREFIX", $tessData, "Machine")
    $env:TESSDATA_PREFIX = $tessData

    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $pathParts = @()
    if ($machinePath) {
        $pathParts = @($machinePath -split ";" | Where-Object { $_ })
    }
    if (-not ($pathParts | Where-Object { $_.TrimEnd("\") -ieq $installDir.TrimEnd("\") })) {
        $newPath = (@($pathParts) + $installDir) -join ";"
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
        $env:Path = "$installDir;$env:Path"
        Write-Log "Added Tesseract install directory to Machine PATH: $installDir"
    } else {
        Write-Log "Tesseract install directory already present in Machine PATH: $installDir"
    }
    Write-Log "Set TESSDATA_PREFIX=$tessData (Machine scope)"
}

function Test-TesseractExecutable {
    param([string]$TesseractExe = "")

    if (-not $TesseractExe) {
        $TesseractExe = Get-TesseractExecutable
    }
    if (-not $TesseractExe) {
        return $false
    }
    try {
        $out = & $TesseractExe --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Tesseract available: $($out | Select-Object -First 1)"
            Set-TesseractEnvironment -TesseractExe $TesseractExe
            return $true
        }
        Write-Log "Tesseract version check failed with exit code $LASTEXITCODE."
        return $false
    } catch {
        Write-Log "Tesseract version check failed: $_"
        return $false
    }
}

function Install-Tesseract {
    if (Test-TesseractExecutable) {
        return $true
    }

    $url = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
    $installDir = Join-Path $env:ProgramFiles "Tesseract-OCR"
    $dst = Join-Path $env:TEMP ("TesseractSetup-{0}.exe" -f ([Guid]::NewGuid().ToString("N")))
    Write-Log "Tesseract not found. Downloading Tesseract OCR installer from UB Mannheim build ..."
    try {
        if (-not (Download-File -Url $url -Destination $dst)) {
            Write-Log "Tesseract installer download failed or produced an empty file."
            return $false
        }
        Write-Log "Downloaded to $dst, running silent Tesseract install ..."
        # UB Mannheim's Tesseract package is NSIS. /S is silent and /D=...
        # must be the final switch; the rest of the line is treated as the path.
        $argLine = '/S /D={0}' -f $installDir
        $p = Start-Process -FilePath $dst -ArgumentList $argLine -PassThru -ErrorAction Stop
        if (-not $p.WaitForExit(600000)) {
            Write-Log "ERROR Tesseract installer timed out after 10 minutes; killing process $($p.Id)."
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            return $false
        }
        Write-Log "Tesseract installer exit code: $($p.ExitCode)"
    } catch {
        Write-Log "ERROR installing Tesseract OCR: $_"
        return $false
    } finally {
        Remove-Item -Path $dst -Force -ErrorAction SilentlyContinue
    }

    $exe = Join-Path $installDir "tesseract.exe"
    return (Test-TesseractExecutable -TesseractExe $exe)
}

function Get-OllamaExecutable {
    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($ollama) {
        return $ollama.Source
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Ollama\ollama.exe")
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Find-OllamaExe {
    return Get-OllamaExecutable
}

function Set-OllamaEnvironment {
    $userProfile = $env:USERPROFILE
    if (-not $userProfile) {
        $userProfile = [Environment]::GetFolderPath("UserProfile")
    }
    $modelsDir = Join-Path $userProfile ".ollama\models"
    New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
    [System.Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "24h", "Machine")
    [System.Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "3", "Machine")
    [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelsDir, "Machine")
    $env:OLLAMA_KEEP_ALIVE = "24h"
    $env:OLLAMA_MAX_LOADED_MODELS = "3"
    $env:OLLAMA_MODELS = $modelsDir
    Write-Log "Set OLLAMA_KEEP_ALIVE=24h, OLLAMA_MAX_LOADED_MODELS=3, and OLLAMA_MODELS=$modelsDir (Machine scope)"
}

function Stop-OllamaProcesses {
    param([string]$Reason = "restart requested")

    Write-Log "Stopping Ollama processes: $Reason"
    Stop-ScheduledTask -TaskName "GuardianNodeOllama" -ErrorAction SilentlyContinue
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Register-OllamaTask {
    param([Parameter(Mandatory=$true)][string]$OllamaExe)

    $taskName = "GuardianNodeOllama"
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $ollamaExeValue = [string]::Join("", @($OllamaExe))
    $OllamaExe = -join ($ollamaExeValue.ToCharArray() | Where-Object { $_ -ne [char]10 -and $_ -ne [char]13 })
    $OllamaExe = $OllamaExe.Trim()
    if (-not $OllamaExe -or -not (Test-Path $OllamaExe)) {
        throw "Ollama executable path is invalid: '$OllamaExe'"
    }
    $wrapperDir = Join-Path $env:ProgramData "GuardianNode"
    New-Item -ItemType Directory -Force -Path $wrapperDir | Out-Null
    $wrapperPath = Join-Path $wrapperDir "ollama_serve_hidden.vbs"
    $wrapperScript = @'
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ollamaPath = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Ollama\ollama.exe"
If Not fso.FileExists(ollamaPath) Then ollamaPath = shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Ollama\ollama.exe"
If Not fso.FileExists(ollamaPath) Then ollamaPath = shell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Ollama\ollama.exe"
cmd = Chr(34) & ollamaPath & Chr(34) & " serve"
shell.Run cmd, 0, True
'@
    [System.IO.File]::WriteAllText($wrapperPath, $wrapperScript + "`r`n", [System.Text.Encoding]::ASCII)
    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument "`"$wrapperPath`"" `
        -WorkingDirectory (Split-Path -Parent $OllamaExe)
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 99 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

    Register-ScheduledTask -TaskName $taskName `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description "GuardianNode local Ollama server for on-device classification" `
        -Force | Out-Null
    Write-Log "Registered scheduled task '$taskName' for $identity."
}

function Start-OllamaServer {
    param([string]$OllamaExe = "")

    if (Test-OllamaReachable) {
        return $true
    }
    $ollamaPath = $OllamaExe
    if (-not $ollamaPath) {
        $ollamaPath = Find-OllamaExe
    }
    if (-not $ollamaPath) {
        Write-Log "Ollama executable was not found."
        return $false
    }
    Write-Log "Starting Ollama server from $ollamaPath ..."
    try {
        Register-OllamaTask -OllamaExe $ollamaPath
        Start-ScheduledTask -TaskName "GuardianNodeOllama" -ErrorAction Stop
        Write-Log "Started scheduled task 'GuardianNodeOllama'."
    } catch {
        Write-Log "WARN could not start GuardianNodeOllama scheduled task: $_"
        Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    }
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-OllamaReachable) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Install-Ollama {
    if (Get-OllamaExecutable) {
        Write-Log "Ollama is installed but not reachable. Starting server ..."
        if (Start-OllamaServer) {
            Write-Log "Ollama is now reachable."
            return $true
        }
    }

    Write-Log "Ollama not reachable at $OllamaUrl. Downloading OllamaSetup.exe ..."
    $url = "https://ollama.com/download/OllamaSetup.exe"
    $dst = Join-Path $env:TEMP ("OllamaSetup-{0}.exe" -f ([Guid]::NewGuid().ToString("N")))
    try {
        if (-not (Download-File -Url $url -Destination $dst)) {
            Write-Log "Ollama installer download failed or produced an empty file."
            return $false
        }
        Write-Log "Downloaded to $dst, running silent install ..."
        # Ollama installer uses /VERYSILENT-style flags or InstallShield; try common ones.
        $p = Start-Process -FilePath $dst -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru -ErrorAction Stop
        Write-Log "Installer exit code: $($p.ExitCode)"
        # Give the service a moment to come up
        Start-Sleep -Seconds 8
        # Set persistent env vars for the Ollama service so models stay hot
        Set-OllamaEnvironment
        if (-not (Test-OllamaReachable)) {
            [void](Start-OllamaServer)
        }
    } catch {
        Write-Log "ERROR installing Ollama: $_"
        return $false
    }

    return (Start-OllamaServer -OllamaExe (Find-OllamaExe))
}

function Get-InstalledModels {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$OllamaUrl/api/tags" -TimeoutSec 10
        $j = $r.Content | ConvertFrom-Json
        $names = @()
        if ($j.models) {
            $names = @($j.models | ForEach-Object { $_.name })
        }
        return ,$names
    } catch {
        Write-Log "WARN could not list installed Ollama models: $_"
        return $null
    }
}

function Pull-Model {
    param([string]$Model)
    if (-not $Model) { return $true }

    $installed = Get-InstalledModels
    if ($null -eq $installed) {
        Write-Log "Ollama model list failed before pulling '$Model'. Restarting Ollama once."
        Stop-OllamaProcesses -Reason "failed model list"
        if (-not (Start-OllamaServer -OllamaExe (Find-OllamaExe))) {
            return $false
        }
        $installed = Get-InstalledModels
    }

    if (($null -ne $installed) -and (@($installed) -contains $Model)) {
        Write-Log "Model '$Model' already installed."
        return $true
    }
    if ($null -eq $installed) {
        Write-Log "ERROR unable to list Ollama models after restart; refusing to start a long pull against an unhealthy server."
        return $false
    }

    Write-Log "Pulling model '$Model' from Ollama registry. This can take several minutes ..."
    $body = @{ name = $Model; stream = $false } | ConvertTo-Json
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$OllamaUrl/api/pull" `
            -Method POST -Body $body -ContentType "application/json" -TimeoutSec 1800
        Write-Log "Pull '$Model': HTTP $($r.StatusCode)"
        return $r.StatusCode -eq 200
    } catch {
        Write-Log "ERROR pulling '$Model': $_"
        return $false
    }
}

# --- Main ---

if (-not (Install-Tesseract)) {
    Write-Log "Tesseract OCR install/check failed. Aborting because screenshot text detection would be unreliable."
    exit 2
}

if ($TesseractOnly) {
    Write-Log "Tesseract-only mode requested. Skipping Ollama entirely."
    exit 0
}

if ($Tier -eq "text_only" -and -not $TextModel) {
    Write-Log "Tier text_only with no LLM. Skipping Ollama entirely (rules engine + Tesseract only)."
    exit 0
}

# Skip Ollama setup if URL is remote; assume the parent's server already has it.
$isLocal = $OllamaUrl -match "://(127\.0\.0\.1|localhost)"
if ($isLocal) {
    Set-OllamaEnvironment
    if (-not (Test-OllamaReachable)) {
        $ollamaExe = Find-OllamaExe
        if ($ollamaExe) {
            if (-not (Start-OllamaServer -OllamaExe $ollamaExe)) {
                Write-Log "Ollama start failed. Aborting model pulls."
                exit 2
            }
        } elseif (-not (Install-Ollama)) {
            Write-Log "Ollama install/start failed. Aborting model pulls."
            exit 2
        }
    } else {
        Write-Log "Ollama already reachable at $OllamaUrl."
    }
} else {
    if (-not (Test-OllamaReachable)) {
        Write-Log "Remote Ollama at $OllamaUrl unreachable. Continuing anyway; backend will retry at runtime."
    } else {
        Write-Log "Remote Ollama reachable."
    }
}

$ok = $true
if ($TextModel)   { if (-not (Pull-Model -Model $TextModel))   { $ok = $false } }
if ($VisionModel) { if (-not (Pull-Model -Model $VisionModel)) { $ok = $false } }
if ($isLocal -and $ok -and -not (Test-OllamaReachable)) {
    Write-Log "Ollama was not reachable after model setup. Restarting persistent task once."
    Stop-OllamaProcesses -Reason "post-pull reachability check"
    if (-not (Start-OllamaServer -OllamaExe (Find-OllamaExe))) {
        $ok = $false
    }
}

if ($ok) {
    Write-Log "All required models installed for tier=$Tier."
    exit 0
} else {
    Write-Log "Model pull failed; backend may degrade to rules-only. Check this log."
    exit 1
}
