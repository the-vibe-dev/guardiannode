# Pause monitoring when you use the PC

When you (the parent) use the kid's PC — to install software, check something for them, or just to use it briefly — you'll want to **pause monitoring** so your own activity isn't logged.

## How to pause

1. Look at the Windows taskbar near the clock. Find the **GuardianNode shield icon** (it may be in the hidden overflow area — click the small `^` arrow).
2. **Right-click** the shield icon.
3. Click **Pause monitoring in parent dashboard**.
4. Sign in to the HTTPS parent dashboard if needed.
5. Open **Devices**, find this PC, and click **Pause 1h**.

The next broker status refresh shows the pause on the child PC. The tray does
not accept or retain a parent password.

## Resuming early

Open the signed-in parent dashboard, go to **Devices**, and click **Resume**.

## Resuming automatically

When the one-hour timer runs out, monitoring resumes on its own.

## What happens during a pause

- No screenshots are captured or sent from the agent.
- The backend records the parent-authorized pause and the broker enforces it on
  the child PC.

## What the kid sees

The child keeps a visible GuardianNode icon. We deliberately do not hide
monitoring status—GuardianNode is not stealth software. A child can open the
dashboard URL from the tray, but cannot authorize a pause without the parent
session.

## "I forgot my password — can I pause?"

Use the recovery phrase to reset dashboard access, then pause from **Devices**.
The recovery phrase never authorizes a child-side action. See
[If you forget your password](if-you-forget-your-password.md).

## Pausing from the dashboard (remote pause)

If you're using a separated setup (kid PC + parent server) and you're on your parent PC, you can pause the child's device from the dashboard. Dashboard pauses are stored server-side and shown in device status:

1. Sign into the dashboard.
2. Click **Devices**.
3. Find the device → click **Pause** → pick duration.

This is the only supported pause authority in the current broker design.

## Pause vs. uninstall

If you want to permanently stop monitoring (e.g. you're transferring the PC, or your kid has aged out), uninstall instead of using a recurring pause. The alpha relies on Windows administrator/UAC permissions for uninstall. See [Troubleshooting](troubleshooting.md) for uninstall instructions.
