param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [ValidateRange(-10, 10)]
    [int]$Rate = -1
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$raw = Get-Content -LiteralPath $ScriptPath -Raw
$body = ($raw -split "`r?`n" | Where-Object {
    $_ -notmatch '^GuardianNode — Guardian Review' -and
    $_ -notmatch '^\[\d:\d\d–\d:\d\d\]$'
}) -join "`n"
$body = [regex]::Replace($body, "(`r?`n){2,}", "`n")

$outputDir = Split-Path -Parent $OutputPath
if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $preferred = $synth.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*' } |
        Select-Object -First 1
    if ($preferred) {
        $synth.SelectVoice($preferred.VoiceInfo.Name)
    }
    $synth.Rate = $Rate
    $synth.Volume = 100
    $synth.SetOutputToWaveFile($OutputPath)
    $synth.Speak($body)
} finally {
    $synth.Dispose()
}

[pscustomobject]@{
    status = "created"
    voice = if ($preferred) { $preferred.VoiceInfo.Name } else { "system default" }
    rate = $Rate
    output = $OutputPath
} | ConvertTo-Json -Compress
