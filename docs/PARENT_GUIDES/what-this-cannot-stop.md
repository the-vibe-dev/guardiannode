# What GuardianNode cannot stop

Real-world honest list of GuardianNode's limits. Read this so you have realistic expectations.

## A determined kid with admin rights

GuardianNode protects against **casual** circumvention. If a kid ends the agent
or the tray from Task Manager, the installer uses clearly named GuardianNode
scheduled tasks, an endpoint broker service, and watchdog services to restart
the supervised components. If the whole thing is killed at once — or the PC is
simply shut down or unplugged — the server notices the device stopped reporting
and surfaces the monitoring gap, so a silent gap doesn't look like "all clear".

What that still does NOT defeat is a determined teenager who:

- Has Windows administrator rights on their PC, AND
- Boots into Safe Mode (where most third-party services are disabled), AND
- Uses the Safe Mode shell to delete the agent files

An administrator can ultimately stop any software on their own machine — no
parental tool can change that. So if your kid is in that category, you have two
options:
1. **Make their Windows account a Standard user** (not Administrator). GuardianNode relies on normal Windows administrator/UAC permissions for uninstall protection in this alpha.
2. **Wait for a future, separately reviewed tamper-resistance tier**. No such
   driver or Safe Mode protection ships in this alpha.

## Encrypted messaging apps with their own crypto

GuardianNode reads what's visible on screen. If your kid uses Signal or another end-to-end-encrypted app, GuardianNode sees only what's displayed — the same as a screenshot. If they switch to disappearing-message mode, GuardianNode catches the message during the seconds it's on screen and OCRs it then.

But:
- If the chat is on a **different device** that GuardianNode doesn't monitor (their phone, a friend's PC, a school Chromebook), we never see it.
- If they use a messaging app GuardianNode doesn't have an OCR region config for, the OCR may be lower quality.

## Phones (iOS or Android)

GuardianNode does not currently have Android or iOS apps. The platform roadmap
is macOS next, then Android, then iOS. Mobile support requires
platform-specific design and is not part of the current alpha.

What you can do on the phone side:
- **iOS Screen Time** — built-in, free, parent-controlled, decent
- **Google Family Link** — built-in for Android, free
- **Bark** (paid) — covers many phone scenarios GuardianNode does not

These are complementary to GuardianNode, not substitutes.

## Voice (Discord voice chat, game voice)

GuardianNode does not record or analyze audio. If grooming happens over voice chat in Discord or in-game voice, GuardianNode doesn't see it.

This is a deliberate scope limit:
- Audio capture is significantly more invasive than text/visual
- Real-time speech-to-text on a home PC is feasible but expensive
- We may revisit in a future version with explicit parent opt-in

## In-game private rooms and ephemeral platforms

Some games (Roblox in particular) have private rooms whose chat we can read from the screen — but only if your kid is using the GuardianNode-monitored PC at the time.

GuardianNode reads whatever is actually visible on the monitored screen, so anything that appears on the PC (Gmail/Outlook web, Discord, chat sites, game chat) can be captured and OCR'd. The flip side: content that never appears on the monitored PC — phone-only apps (Snapchat, BeReal), or sessions on another device — is invisible to it.

## Brand-new scam variants

The LLM classifier and rules engine catch most known patterns. Brand-new scam scripts (especially with novel coded language) may slip past on first contact. Reporting false negatives via the `safety_concern` issue template helps train future rules updates.

## Sufficiently sophisticated grooming

A patient adult who:
- Builds rapport over weeks before escalating
- Uses entirely innocent-sounding language in monitored channels
- Moves the kid to an unmonitored channel before any red flags appear

…can defeat any automated detection. The signs you might still catch:
- The "let's talk somewhere else" pivot (we flag this strongly)
- The "don't tell your parents" phrase (high-confidence rule trigger)
- Personal-info requests (school, address, phone)

Combined with conversations with your kid and noticing real-world behavior
changes, GuardianNode may help surface concerning signals. It cannot catch
everything.

## Things on the school Chromebook

If the school issued a locked-down Chromebook, you cannot install third-party software (including GuardianNode, which is a Windows agent). Ask the school what they monitor — most school-issued devices have Gaggle, Bark, GoGuardian, or similar.

## VPN circumvention

If your kid runs a VPN on their PC, visible on-screen content can still be
captured by GuardianNode's local agent before network traffic reaches the VPN.
VPNs can still interfere with network-level enforcement integrations such as
Pi-hole/AdGuard.

## Bottom line

GuardianNode is **one of several tools**. The most important child-safety tool is **talking to your kid**. The second-most-important is **knowing who they spend time with**. GuardianNode is third — assistive software that catches things that would otherwise be invisible to you.

If you're seeing concerning signals, don't wait for the next alert. Have the conversation.
