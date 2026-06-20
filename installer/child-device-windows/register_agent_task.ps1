# Registers the GuardianNode agent as a Task Scheduler logon task for ALL users.
#
# Why a task and not a service: Windows services run in session 0 and cannot
# see or capture a logged-in user's desktop. A logon task with a BUILTIN\Users
# group principal runs the agent inside every user's own session at sign-in.
# The agent has a per-session single-instance mutex, so this can never stack.
#
# Tamper resistance: the task itself restarts on failure, and the SYSTEM-level
# GuardianNodeWatchdog service re-runs the task if the process disappears.
param(
    [Parameter(Mandatory = $true)][string]$AgentExe,
    [string]$TaskName = "GuardianNodeAgent"
)

$ErrorActionPreference = "Stop"

# Resolve BUILTIN\Users by SID so this works on non-English Windows.
$usersGroup = (New-Object System.Security.Principal.SecurityIdentifier("S-1-5-32-545")).
    Translate([System.Security.Principal.NTAccount]).Value

$action = New-ScheduledTaskAction -Execute $AgentExe -WorkingDirectory (Split-Path -Parent $AgentExe)
# Note: this script registers ONE task (agent or tray) per call; the installer
# invokes it twice. Both run in the user's session at logon and on demand
# (the watchdog re-runs them with schtasks /Run if the process is killed).
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -GroupId $usersGroup -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "GuardianNode monitoring agent (visible in the system tray; see PRIVACY.md in the install folder)" `
    -Force | Out-Null

Write-Output "Registered scheduled task '$TaskName' for group '$usersGroup'."

# Start it now for the user who is installing, so monitoring begins without a reboot.
try {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Started '$TaskName'."
} catch {
    Write-Output "Task registered; it will start at next logon ($_)."
}
