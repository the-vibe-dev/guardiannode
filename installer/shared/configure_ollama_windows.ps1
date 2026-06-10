# GuardianNode — Windows Ollama bootstrap.
#
# Called by the Inno Setup installer's [Run] section. Receives:
#   -Tier <full | vision_only | text_only>
#   -TextModel <ollama model tag, optional>
#   -VisionModel <ollama model tag, optional>
#   -OllamaUrl <http://host:port> (defaults to local)
#
# Behavior:
#   1. Check if Ollama is reachable. If not, download + silent-install Ollama for Windows.
#   2. Pull the required models for the chosen tier (skip if already pulled).
#   3. Configure Ollama service env: OLLAMA_MAX_LOADED_MODELS, OLLAMA_KEEP_ALIVE.
#   4. Print final summary; exit 0 on success, non-zero on failure.

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("full","vision_only","text_only")]
    [string]$Tier,

    [string]$TextModel = "",
    [string]$VisionModel = "",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$LogPath = "C:\ProgramData\GuardianNode\logs\install-ollama.log"
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

# Pick default models per tier if not explicitly given
if (-not $TextModel) {
    switch ($Tier) {
        "full"        { $TextModel = "llama3.2:3b" }
        "text_only"   { $TextModel = "llama3.2:1b" }
        "vision_only" { $TextModel = "" }
    }
}
if (-not $VisionModel) {
    switch ($Tier) {
        "full"        { $VisionModel = "qwen2.5vl:7b" }
        "vision_only" { $VisionModel = "qwen2.5vl:7b" }
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

function Install-Ollama {
    Write-Log "Ollama not reachable at $OllamaUrl. Downloading OllamaSetup.exe ..."
    $url = "https://ollama.com/download/OllamaSetup.exe"
    $dst = Join-Path $env:TEMP "OllamaSetup.exe"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dst -TimeoutSec 600
        Write-Log "Downloaded to $dst, running silent install ..."
        # Ollama installer uses /VERYSILENT-style flags or InstallShield; try common ones.
        $p = Start-Process -FilePath $dst -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru -ErrorAction Stop
        Write-Log "Installer exit code: $($p.ExitCode)"
        # Give the service a moment to come up
        Start-Sleep -Seconds 8
        # Set persistent env vars for the Ollama service so models stay hot
        [System.Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "24h", "Machine")
        [System.Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "3", "Machine")
        Write-Log "Set OLLAMA_KEEP_ALIVE=24h and OLLAMA_MAX_LOADED_MODELS=3 (Machine scope)"
    } catch {
        Write-Log "ERROR installing Ollama: $_"
        return $false
    }

    # Wait for it to come online
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-OllamaReachable) { Write-Log "Ollama is now reachable."; return $true }
        Start-Sleep -Seconds 2
    }
    Write-Log "Ollama did not become reachable after install."
    return $false
}

function Get-InstalledModels {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$OllamaUrl/api/tags" -TimeoutSec 10
        $j = $r.Content | ConvertFrom-Json
        return @($j.models | ForEach-Object { $_.name })
    } catch {
        return @()
    }
}

function Pull-Model {
    param([string]$Model)
    if (-not $Model) { return $true }

    $installed = Get-InstalledModels
    if ($installed -contains $Model) {
        Write-Log "Model '$Model' already installed."
        return $true
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

if ($Tier -eq "text_only" -and -not $TextModel) {
    Write-Log "Tier text_only with no LLM. Skipping Ollama entirely (rules engine + Tesseract only)."
    exit 0
}

# Skip Ollama setup if URL is remote — assume the parent's server already has it.
$isLocal = $OllamaUrl -match "://(127\.0\.0\.1|localhost)"
if ($isLocal) {
    if (-not (Test-OllamaReachable)) {
        if (-not (Install-Ollama)) {
            Write-Log "Ollama install/start failed. Aborting model pulls."
            exit 2
        }
    } else {
        Write-Log "Ollama already reachable at $OllamaUrl."
    }
} else {
    if (-not (Test-OllamaReachable)) {
        Write-Log "Remote Ollama at $OllamaUrl unreachable. Continuing anyway — backend will retry at runtime."
    } else {
        Write-Log "Remote Ollama reachable."
    }
}

$ok = $true
if ($TextModel)   { if (-not (Pull-Model -Model $TextModel))   { $ok = $false } }
if ($VisionModel) { if (-not (Pull-Model -Model $VisionModel)) { $ok = $false } }

if ($ok) {
    Write-Log "All required models installed for tier=$Tier."
    exit 0
} else {
    Write-Log "Model pull failed; backend may degrade to rules-only. Check this log."
    exit 1
}
