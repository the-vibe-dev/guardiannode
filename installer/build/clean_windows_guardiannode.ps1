param(
  [string]$LogPath = "$env:TEMP\guardiannode-clean.log",
  [switch]$KeepData
)

$ErrorActionPreference = "Continue"

function Write-CleanLog {
  param([string]$Message)
  $Message | Out-File -Append -Encoding utf8 $LogPath
}

New-Item -ItemType Directory -Force (Split-Path -Parent $LogPath) | Out-Null
"clean start $(Get-Date -Format o)" | Out-File -Encoding utf8 $LogPath

$services = @(
  "GuardianNodeWatchdog2",
  "EndpointHealthAgent",
  "GuardianNodeWatchdog",
  "GuardianNodeAgent",
  "GuardianNodeBackend",
  "GuardianNodeBroker"
)
foreach ($svc in $services) {
  sc.exe stop $svc | Out-File -Append -Encoding utf8 $LogPath
  sc.exe delete $svc | Out-File -Append -Encoding utf8 $LogPath
}

foreach ($task in @("GuardianNodeAgent", "GuardianNodeTray", "GuardianNodeOllama")) {
  schtasks.exe /End /TN $task | Out-File -Append -Encoding utf8 $LogPath
  schtasks.exe /Delete /TN $task /F | Out-File -Append -Encoding utf8 $LogPath
}

foreach ($proc in @("GuardianNodeAgent", "GuardianNodeTray", "GuardianNodeWatchdog", "GuardianNodeBackend", "GuardianNodeBroker", "ollama", "llama-server")) {
  taskkill.exe /IM "$proc.exe" /F | Out-File -Append -Encoding utf8 $LogPath
}

$uninstallers = @(
  "C:\Program Files\GuardianNode\unins000.exe",
  "C:\Program Files\GuardianNodeServer\unins000.exe",
  "C:\Program Files (x86)\GuardianNode\unins000.exe",
  "C:\Program Files (x86)\GuardianNodeServer\unins000.exe"
)
foreach ($u in $uninstallers) {
  if (Test-Path $u) {
    $p = Start-Process -FilePath $u -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
    Write-CleanLog "uninstaller $u exit=$($p.ExitCode)"
  }
}

$paths = @(
  "C:\Program Files\GuardianNode",
  "C:\Program Files\GuardianNodeServer",
  "C:\Program Files (x86)\GuardianNode",
  "C:\Program Files (x86)\GuardianNodeServer"
)
if (!$KeepData) {
  $paths += "C:\ProgramData\GuardianNode"
}

foreach ($path in $paths) {
  if (Test-Path $path) {
    Remove-Item -Recurse -Force $path
    Write-CleanLog "removed $path"
  }
}

netsh.exe advfirewall firewall delete rule name="GuardianNode Backend (LAN)" protocol=TCP localport=8787 |
  Out-File -Append -Encoding utf8 $LogPath
netsh.exe advfirewall firewall delete rule name="GuardianNode Backend (Private LAN)" |
  Out-File -Append -Encoding utf8 $LogPath

Write-CleanLog "clean done $(Get-Date -Format o)"
Get-Content $LogPath -Tail 80
