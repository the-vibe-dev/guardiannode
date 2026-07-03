param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$OutputRoot = (Join-Path $ProjectRoot "installer\build\prebuilt"),
  [string]$PythonLauncher = "py",
  [string]$PythonVersion = "-3",
  [switch]$SkipBackend,
  [switch]$SkipAgent
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
  param(
    [string]$Exe,
    [string[]]$Arguments,
    [string]$WorkingDirectory = $ProjectRoot
  )
  Push-Location $WorkingDirectory
  try {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Reset-Directory {
  param([string]$Path)
  if (Test-Path $Path) {
    Remove-Item -Recurse -Force $Path
  }
  New-Item -ItemType Directory -Force $Path | Out-Null
}

function New-BuildVenv {
  param([string]$Path)
  if (!(Test-Path (Join-Path $Path "Scripts\python.exe"))) {
    Invoke-Checked $PythonLauncher @($PythonVersion, "-m", "venv", $Path) | Out-Host
  }
  $venvPython = Join-Path $Path "Scripts\python.exe"
  Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools") | Out-Host
  return $venvPython
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force $OutputRoot | Out-Null

if (!$SkipBackend) {
  Write-Host "Building GuardianNodeBackend PyInstaller bundle..."
  $backendVenv = Join-Path $ProjectRoot ".venv-backend-build"
  $backendPython = New-BuildVenv $backendVenv
  Invoke-Checked $backendPython @("-m", "pip", "install", "-e", (Join-Path $ProjectRoot "backend"), "pyinstaller")
  Invoke-Checked $backendPython @("-m", "PyInstaller", "--clean", "--noconfirm", "guardiannode_backend.spec") (Join-Path $ProjectRoot "backend")

  $backendDist = Join-Path $ProjectRoot "backend\dist\GuardianNodeBackend"
  if (!(Test-Path (Join-Path $backendDist "GuardianNodeBackend.exe"))) {
    throw "Backend build did not produce GuardianNodeBackend.exe"
  }
  $backendOut = Join-Path $OutputRoot "backend"
  Reset-Directory $backendOut
  Copy-Item -Recurse -Force (Join-Path $backendDist "*") $backendOut
}

if (!$SkipAgent) {
  Write-Host "Building GuardianNodeAgent PyInstaller bundle..."
  $agentVenv = Join-Path $ProjectRoot ".venv-agent-build"
  $agentPython = New-BuildVenv $agentVenv
  $agentProject = Join-Path $ProjectRoot "agent-windows"
  Invoke-Checked $agentPython @("-m", "pip", "install", "-e", "${agentProject}[windows]", "pyinstaller")
  Invoke-Checked $agentPython @("-m", "PyInstaller", "--clean", "--noconfirm", "guardiannode_agent.spec") $agentProject

  $agentDist = Join-Path $agentProject "dist\GuardianNodeAgent"
  foreach ($exeName in @("GuardianNodeAgent.exe", "GuardianNodeTray.exe", "GuardianNodeWatchdog.exe")) {
    if (!(Test-Path (Join-Path $agentDist $exeName))) {
      throw "Agent build did not produce $exeName"
    }
  }
  $agentOut = Join-Path $OutputRoot "agent"
  Reset-Directory $agentOut
  Copy-Item -Recurse -Force (Join-Path $agentDist "*") $agentOut
}

Write-Host "Windows bundles ready under $OutputRoot"
Get-ChildItem -Recurse -File $OutputRoot |
  Where-Object { $_.Name -like "GuardianNode*.exe" } |
  Select-Object FullName, Length
