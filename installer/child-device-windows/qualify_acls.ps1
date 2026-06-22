param(
    [string]$DataRoot = "$env:ProgramData\GuardianNode",
    [string]$InstallRoot = "$env:ProgramFiles\GuardianNode",
    [string]$OutputDir = "$env:ProgramData\GuardianNode\logs\qualification",
    [switch]$AllowMissing
)

$ErrorActionPreference = "Stop"

$lowPrivilegeSids = @(
    "S-1-1-0",       # Everyone
    "S-1-5-4",       # Interactive
    "S-1-5-11",      # Authenticated Users
    "S-1-5-32-545"   # Builtin Users
)

$protectedPaths = @(
    "$DataRoot\Secure",
    "$DataRoot\Secure\device.json",
    "$DataRoot\Secure\parent.json",
    "$DataRoot\Secure\pause_state.json",
    "$DataRoot\Secure\maintenance.flag",
    "$DataRoot\AgentSecure",
    "$DataRoot\AgentSecure\queue.sqlite",
    "$DataRoot\AgentSecure\queue.key",
    "$DataRoot\keys\setup_token.json",
    "$DataRoot\keys\device_bootstrap_token.json",
    "$DataRoot\keys\master.key",
    "$DataRoot\keys\master.key.dpapi",
    "$DataRoot\server.env"
)

$services = @(
    "GuardianNodeBroker",
    "GuardianNodeBackend",
    "GuardianNodeWatchdog",
    "GuardianNodeWatchdog2"
)

$tasks = @(
    "GuardianNodeAgent",
    "GuardianNodeTray"
)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-Section {
    param([string]$Message)
    Write-Host "== $Message =="
}

function Resolve-Sid {
    param([System.Security.Principal.IdentityReference]$Identity)
    try {
        return $Identity.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $Identity.Value
    }
}

function Test-RightsOverlap {
    param(
        [System.Security.AccessControl.FileSystemRights]$Rights,
        [System.Security.AccessControl.FileSystemRights]$Mask
    )
    return (($Rights -band $Mask) -ne 0)
}

function Assert-ProtectedPath {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        if ($AllowMissing) {
            Write-Warning "Missing protected path (allowed for partial install): $Path"
            return
        }
        throw "Missing protected path: $Path"
    }

    $acl = Get-Acl -LiteralPath $Path
    $systemFull = $false
    $adminsFull = $false
    $badRules = @()
    $dangerousRights =
        [System.Security.AccessControl.FileSystemRights]::Read -bor
        [System.Security.AccessControl.FileSystemRights]::Write -bor
        [System.Security.AccessControl.FileSystemRights]::Modify -bor
        [System.Security.AccessControl.FileSystemRights]::FullControl

    foreach ($rule in $acl.Access) {
        $sid = Resolve-Sid $rule.IdentityReference
        if ($rule.AccessControlType -eq "Allow") {
            if ($sid -eq "S-1-5-18" -and (Test-RightsOverlap $rule.FileSystemRights ([System.Security.AccessControl.FileSystemRights]::FullControl))) {
                $systemFull = $true
            }
            if ($sid -eq "S-1-5-32-544" -and (Test-RightsOverlap $rule.FileSystemRights ([System.Security.AccessControl.FileSystemRights]::FullControl))) {
                $adminsFull = $true
            }
            if ($lowPrivilegeSids -contains $sid) {
                if (Test-RightsOverlap $rule.FileSystemRights $dangerousRights) {
                    $badRules += "$Path grants $($rule.FileSystemRights) to $($rule.IdentityReference)"
                }
            }
        }
    }

    if (-not $systemFull) {
        throw "$Path does not grant LocalSystem FullControl"
    }
    if (-not $adminsFull) {
        throw "$Path does not grant Builtin Administrators FullControl"
    }
    if ($badRules.Count -gt 0) {
        throw ($badRules -join [Environment]::NewLine)
    }
}

function Assert-ServiceDacl {
    param([string]$Name)
    $result = & sc.exe sdshow $Name 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($AllowMissing) {
            Write-Warning "Missing service (allowed for partial install): $Name"
            return
        }
        throw "Could not read service SDDL for ${Name}: $result"
    }
    $text = ($result | Out-String).Trim()
    if ($text -match "\(D;;") {
        throw "$Name uses explicit deny ACEs; service DACL must be allow-only"
    }
    if ($text -notmatch "SY" -or $text -notmatch "BA") {
        throw "$Name SDDL must include LocalSystem and Builtin Administrators"
    }
}

Write-Section "Collecting raw ACL evidence"
& icacls.exe $DataRoot /T /C | Out-File -Encoding utf8 (Join-Path $OutputDir "icacls-guardiannode.txt")

$aclRows = foreach ($path in $protectedPaths) {
    if (Test-Path -LiteralPath $path) {
        Get-Acl -LiteralPath $path | Select-Object Path, Owner, Group, AccessToString
    }
}
$aclRows | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $OutputDir "get-acl-protected.json")

Write-Section "Collecting service descriptors"
$serviceReport = foreach ($service in $services) {
    $sd = & sc.exe sdshow $service 2>&1
    [pscustomobject]@{
        Service = $service
        ExitCode = $LASTEXITCODE
        Sddl = ($sd | Out-String).Trim()
    }
}
$serviceReport | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $OutputDir "service-sddl.json")

Write-Section "Collecting scheduled task XML"
foreach ($task in $tasks) {
    $xmlPath = Join-Path $OutputDir "$task.xml"
    & schtasks.exe /Query /TN $task /XML 2>$null | Out-File -Encoding utf8 $xmlPath
}

Write-Section "Asserting protected filesystem ACLs"
foreach ($path in $protectedPaths) {
    Assert-ProtectedPath -Path $path
}

Write-Section "Asserting service DACLs"
foreach ($service in $services) {
    Assert-ServiceDacl -Name $service
}

Write-Host "GuardianNode Windows ACL qualification passed. Evidence: $OutputDir"
