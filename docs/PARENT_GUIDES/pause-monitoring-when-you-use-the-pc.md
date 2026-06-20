# Pause monitoring when you use the PC

When you (the parent) use the kid's PC — to install software, check something for them, or just to use it briefly — you'll want to **pause monitoring** so your own activity isn't logged.

## How to pause

1. Look at the Windows taskbar near the clock. Find the **GuardianNode shield icon** (it may be in the hidden overflow area — click the small `^` arrow).
2. **Right-click** the shield icon.
3. Click **Pause monitoring**.
4. Enter your **parent password**.
5. Pick how long:
   - **15 minutes** — for a quick check
   - **1 hour** — for normal parent use
   - **4 hours** — for a longer session
   - **Until reboot** — pauses until the PC restarts
6. Click **OK**.

The shield icon turns **yellow** while paused. Hovering over it shows the countdown timer.

## Resuming early

Right-click the yellow shield → **Resume monitoring** → enter parent password.

## Resuming automatically

When the timer runs out, monitoring resumes on its own and the icon goes back to green.

## What happens during a pause

- No screenshots are captured or sent from the agent.
- Local tray pauses are enforced on the child PC. In this alpha they are not
  synced to the dashboard audit log.

## What the kid sees

The kid sees the same yellow icon you do. We deliberately don't hide pauses from them — GuardianNode is not stealth software. Knowing that you paused for an hour while doing something they couldn't see is fine; them being able to *trigger* a pause is not.

## "I forgot my password — can I pause?"

No. The pause requires the parent password (or the recovery code as a fallback). This is intentional — otherwise the kid could pause whenever they wanted. See [If you forget your password](if-you-forget-your-password.md).

## Pausing from the dashboard (remote pause)

If you're using a separated setup (kid PC + parent server) and you're on your parent PC, you can pause the child's device from the dashboard. Dashboard pauses are stored server-side and shown in device status:

1. Sign into the dashboard.
2. Click **Devices**.
3. Find the device → click **Pause** → pick duration.

This is convenient if you're physically away from the kid's PC.

## Pause vs. uninstall

If you want to permanently stop monitoring (e.g. you're transferring the PC, or your kid has aged out), uninstall instead of using a recurring pause. The alpha relies on Windows administrator/UAC permissions for uninstall. See [Troubleshooting](troubleshooting.md) for uninstall instructions.
