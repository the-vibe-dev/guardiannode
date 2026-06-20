param(
    [string]$TokenPath = "$env:ProgramData\GuardianNode\keys\setup_token.json"
)

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-TokenPath", "`"$TokenPath`""
    ) -join " "
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $args
    exit
}

if (Test-Path $TokenPath) {
    try {
        $token = (Get-Content $TokenPath -Raw | ConvertFrom-Json).token
        Write-Host ""
        Write-Host "GuardianNode one-time setup token:"
        Write-Host ""
        Write-Host "  $token"
        Write-Host ""
    } catch {
        Write-Host "Setup token file exists, but could not be parsed: $($_.Exception.Message)"
    }
} else {
    Write-Host "Setup token file not found at $TokenPath"
}

Read-Host "Press Enter to close"
