param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$ServerUrl,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$ServerUrl = $ServerUrl.TrimEnd('/')
$uri = $null
if (-not [Uri]::TryCreate($ServerUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -ne 'https' -or $uri.AbsolutePath -ne '/' -or
    $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
    throw 'The replacement server URL must be an HTTPS origin.'
}

$securePath = Join-Path $DataRoot 'Secure\device.json'
$legacyPath = Join-Path $DataRoot 'device.json'
$credentialPaths = @(@($securePath, $legacyPath) | Where-Object { Test-Path -LiteralPath $_ })
if ($credentialPaths.Count -eq 0) {
    throw 'The child is not paired; use a new pairing bundle instead.'
}
$credential = Get-Content -LiteralPath $credentialPaths[0] -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $credential.device_id -or -not $credential.device_token -or
    -not $credential.ca_path -or -not $credential.ca_sha256) {
    throw 'The paired device credential or family CA pin is incomplete.'
}
$caPath = [string]$credential.ca_path
if (-not (Test-Path -LiteralPath $caPath -PathType Leaf)) {
    throw 'The enrolled family CA file is missing.'
}
$ca = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($caPath)
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $actual = [BitConverter]::ToString($sha.ComputeHash($ca.RawData)).Replace('-', '').ToLowerInvariant()
} finally {
    $sha.Dispose()
}
if ($actual -ne ([string]$credential.ca_sha256).ToLowerInvariant().Replace(':', '')) {
    throw 'The enrolled family CA file does not match the saved pin.'
}

# Schannel cannot check revocation for this private family CA. This flag skips
# revocation lookup while retaining CA-chain and hostname verification.
& curl.exe --fail --silent --show-error --ssl-no-revoke --max-time 15 `
    --cacert $caPath --output NUL "$ServerUrl/api/health/ready"
if ($LASTEXITCODE -ne 0) {
    throw 'The replacement server did not pass the saved family CA check.'
}
if ($ValidateOnly) {
    Write-Output 'Replacement server verified with the enrolled family CA.'
    exit 0
}

$configPath = Join-Path $DataRoot 'agent.yaml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw 'The installed child configuration is missing.'
}
$lines = [IO.File]::ReadAllLines($configPath)
$found = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*backend_url\s*:') {
        $lines[$i] = 'backend_url: ' + $ServerUrl
        $found = $true
    }
}
if (-not $found) {
    throw 'The installed child configuration has no backend URL.'
}

$encoding = New-Object System.Text.UTF8Encoding($false)
$changes = New-Object System.Collections.ArrayList
$configText = [string]::Join([Environment]::NewLine, $lines) + [Environment]::NewLine
[void]$changes.Add(@{ Path = $configPath; Text = $configText })
foreach ($path in $credentialPaths) {
    $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $record.device_id -or -not $record.device_token) {
        throw 'An installed device credential is incomplete.'
    }
    $record.backend_url = $ServerUrl
    [void]$changes.Add(@{ Path = $path; Text = ($record | ConvertTo-Json -Compress -Depth 10) + [Environment]::NewLine })
}

$replaced = New-Object System.Collections.ArrayList
try {
    foreach ($change in $changes) {
        $temp = $change.Path + '.relocating'
        $backup = $change.Path + '.pre-relocation'
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
        [IO.File]::WriteAllText($temp, $change.Text, $encoding)
        [IO.File]::Replace($temp, $change.Path, $backup, $true)
        [void]$replaced.Add(@{ Path = $change.Path; Backup = $backup })
    }
} catch {
    foreach ($change in $replaced) {
        if (Test-Path -LiteralPath $change.Backup) {
            Copy-Item -LiteralPath $change.Backup -Destination $change.Path -Force
        }
    }
    throw
} finally {
    foreach ($change in $changes) {
        $temp = $change.Path + '.relocating'
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}
foreach ($change in $replaced) {
    Remove-Item -LiteralPath $change.Backup -Force
}
Write-Output 'Child server address updated; device identity and family CA pin preserved.'
