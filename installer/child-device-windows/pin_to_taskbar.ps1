# Pin a target executable to the current user's Windows taskbar.
#
# Background: Microsoft progressively locked down programmatic taskbar pinning.
# The legacy COM verb ("Pin to Tas&kbar") still exists in shell32 but, on
# Windows 11 22H2 and later, invoking it on the real namespace path does
# nothing. The supported workaround (originally from a Win11 community thread,
# widely confirmed) is:
#   1. Read the verb's ExplorerCommandHandler CLSID from HKLM.
#   2. Register a temporary class under HKCU that exposes the same handler.
#   3. Invoke that temporary verb on the target file via Shell.Application.
#   4. Remove the temp class.
#
# This must run AS THE END USER (not the elevated installer), because
# taskbar layout is a per-user setting and HKCU is the user's hive. The
# installer should call this with the `runasoriginaluser` flag.

param(
  [Parameter(Mandatory = $true)]
  [string]$Target
)

$ErrorActionPreference = "Stop"

function Write-Log {
  param([string]$Message)
  $logDir = Join-Path $env:ProgramData "GuardianNode\logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path (Join-Path $logDir "install.log") -Value "$ts  pin_to_taskbar  $Message"
}

if (-not (Test-Path $Target)) {
  Write-Log "target not found: $Target - skipping pin"
  exit 0
}

try {
  # Step 1: read the canonical taskbar-pin verb's handler CLSID.
  $handlerKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\Windows.taskbarpin"
  $handler = (Get-ItemProperty -Path $handlerKey -Name ExplorerCommandHandler -ErrorAction Stop).ExplorerCommandHandler
  if (-not $handler) { throw "ExplorerCommandHandler not found in HKLM" }

  # Step 2: stage a temporary verb on a private class in HKCU.
  $tempVerb = "guardiannode-pin"
  $classKey = "HKCU:\Software\Classes\*\shell\$tempVerb"
  New-Item -Path $classKey -Force | Out-Null
  Set-ItemProperty -Path $classKey -Name "ExplorerCommandHandler" -Value $handler

  # Step 3: invoke the temp verb on the target.
  $folder = Split-Path -Parent $Target
  $leaf   = Split-Path -Leaf   $Target
  $shell  = New-Object -ComObject Shell.Application
  $item   = $shell.Namespace($folder).ParseName($leaf)
  if ($null -eq $item) { throw "Shell.Application could not resolve $Target" }
  $item.InvokeVerb($tempVerb)

  # Step 4: clean up.
  Remove-Item -Path $classKey -Recurse -Force -ErrorAction SilentlyContinue

  Write-Log "pinned $Target to taskbar"
  exit 0
} catch {
  # Best-effort: a failure here should NOT abort installation. The Start Menu
  # shortcut still exists and the user can right-click -> Pin to taskbar by hand.
  Write-Log "pin failed (non-fatal): $($_.Exception.Message)"
  exit 0
}
