param(
    [string]$WorkDir = "C:\GuardianNodeQualification"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$fixture = Join-Path $WorkDir "synthetic-gaming-chat.html"
$imageFixture = Join-Path $WorkDir "synthetic-gaming-chat.png"
$html = @"
<!doctype html>
<html>
<head>
  <title>Synthetic game chat - GuardianNode demo</title>
  <style>
    body { font-family: Segoe UI, sans-serif; background: #f8fafc; color: #172033; padding: 6vh 8vw; }
    h1 { color: #2563eb; font-size: 42px; }
    p { font-size: 34px; line-height: 1.5; }
    .label { font-size: 24px; color: #64748b; }
  </style>
</head>
<body>
  <div class="label">SYNTHETIC DEMO - NO REAL PEOPLE OR FAMILY DATA</div>
  <h1>Competitive game team chat</h1>
  <p>That boss wiped us again. kys and respawn before the next round, lol.</p>
  <div class="label">Context: fictional competitive game match</div>
</body>
</html>
"@
[System.IO.File]::WriteAllText($fixture, $html, [System.Text.UTF8Encoding]::new($false))

Add-Type -AssemblyName System.Drawing
$bitmap = [System.Drawing.Bitmap]::new(1600, 900)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.Clear([System.Drawing.Color]::FromArgb(248, 250, 252))
    $labelFont = [System.Drawing.Font]::new("Segoe UI", 22)
    $titleFont = [System.Drawing.Font]::new("Segoe UI", 38, [System.Drawing.FontStyle]::Bold)
    $bodyFont = [System.Drawing.Font]::new("Segoe UI", 34)
    $muted = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(100, 116, 139))
    $blue = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(37, 99, 235))
    $ink = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(23, 32, 51))
    $graphics.DrawString("SYNTHETIC DEMO - NO REAL PEOPLE OR FAMILY DATA", $labelFont, $muted, 110, 100)
    $graphics.DrawString("Competitive game team chat", $titleFont, $blue, 110, 190)
    $graphics.DrawString("That boss wiped us again. kys and respawn`nbefore the next round, lol.", $bodyFont, $ink, 110, 310)
    $graphics.DrawString("Context: fictional competitive game match", $labelFont, $muted, 110, 560)
    $bitmap.Save($imageFixture, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

$taskName = "GuardianNodeQualificationSyntheticIncident"
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Get-Process mspaint -ErrorAction SilentlyContinue | Stop-Process -Force
$taskUser = (Get-ScheduledTask -TaskName $taskName).Principal.UserId
$paint = "C:\Users\$taskUser\AppData\Local\Microsoft\WindowsApps\mspaint.exe"
if (-not (Test-Path $paint)) {
    throw "Paint is unavailable for the interactive qualification user."
}
$action = New-ScheduledTaskAction -Execute $paint -Argument "`"$imageFixture`""
Set-ScheduledTask -TaskName $taskName -Action $action | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

Stop-ScheduledTask -TaskName "GuardianNodeAgent" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "GuardianNodeAgent"
Start-Sleep -Seconds 3

[pscustomobject]@{
    fixture = Test-Path $fixture
    display_task = (Get-ScheduledTask -TaskName $taskName).State.ToString()
    agent = (Get-ScheduledTask -TaskName "GuardianNodeAgent").State.ToString()
} | ConvertTo-Json -Compress
