param(
    [string]$BundlePath = (Join-Path $PSScriptRoot "..\dist\GuardianNodeAgent")
)

$ErrorActionPreference = "Stop"
$bundle = (Resolve-Path $BundlePath).Path

function Get-PeSubsystem {
    param([Parameter(Mandatory = $true)][string]$Path)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 256) {
        throw "$Path is too small to be a PE executable"
    }

    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $optionalHeader = $peOffset + 24
    $magic = [BitConverter]::ToUInt16($bytes, $optionalHeader)
    if ($magic -ne 0x10b -and $magic -ne 0x20b) {
        throw "$Path has an unsupported PE optional-header magic"
    }

    return [BitConverter]::ToUInt16($bytes, $optionalHeader + 68)
}

function Assert-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Subsystem,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $path = Join-Path $bundle $Name
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "Missing bundle executable: $path"
    }

    $actualSubsystem = Get-PeSubsystem -Path $path
    if ($actualSubsystem -ne $Subsystem) {
        throw "$Name uses PE subsystem $actualSubsystem; expected $Subsystem"
    }

    $process = Start-Process -FilePath $path -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$Name $($Arguments -join ' ') exited with code $($process.ExitCode)"
    }
}

Assert-Executable -Name "GuardianNodeAgent.exe" -Subsystem 2 -Arguments @("--version")
Assert-Executable -Name "GuardianNodeTray.exe" -Subsystem 2 -Arguments @("--self-test")
Assert-Executable -Name "GuardianNodeWatchdog.exe" -Subsystem 3 -Arguments @("--help")

Write-Host "GuardianNode Windows bundle verification passed."
