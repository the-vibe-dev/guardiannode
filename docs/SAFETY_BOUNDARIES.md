# Safety Boundaries

A short, honest statement of what GuardianNode does, what it doesn't, and where the lines are.

## What this software is

GuardianNode is **scoped, visible, parent-operated** monitoring software. It exists to help parents detect online risks to their children — grooming, scams, bullying, self-harm signals, explicit content — without sending child data to a cloud provider.

It is one tool among many. It is not a substitute for:

- Talking with your kid about online safety
- Knowing the people in your kid's life
- Professional support (counselors, therapists, doctors)
- Emergency services when there is imminent danger

## What this software is NOT

### NOT stealth/spyware

- A visible tray icon shows on the child's PC when monitoring is active.
- The agent appears in Programs & Features and Task Manager — it is not hidden.
- The child can see when monitoring is paused.
- The audit log helps parents have an honest conversation with their kid about why monitoring exists.

We will not accept code contributions that hide the agent's presence from the device's user.

### NOT a system-wide keylogger

- No raw keystroke capture API hooks.
- Current alpha installers enable visible desktop screenshot capture by default.
  Depending on policy/config, GuardianNode may capture the full visible screen
  or capture only when configured apps are active.
- No global hooks, no keyboard input drivers, no IME-level capture.

### NOT for monitoring adults without consent

GuardianNode is designed for parents monitoring their own minor children's devices. It is not designed for:

- Spousal surveillance
- Employer monitoring of employees
- Stalking, of any kind, of any person
- Monitoring of adults (18+) who have not consented in writing

We will not provide support, documentation, or feature work to enable these uses. Many of them are illegal in many jurisdictions.

### NOT a CSAM scanner

We do not scan for CSAM hashes (e.g. PhotoDNA). That work belongs in dedicated reporting infrastructure operated by law enforcement and certified providers (NCMEC in the US). If GuardianNode's vision classifier flags content that you believe is CSAM:

1. Do NOT redistribute or "preserve" the file yourself beyond what GuardianNode encrypts.
2. Contact local law enforcement immediately (911 in the US for imminent harm; otherwise your local FBI field office or NCMEC CyberTipline: 1-800-843-5678).
3. Follow law enforcement's instructions. They will tell you what evidence to preserve and how.

Export creates a locally encrypted archive for parent backup and review. It is
not a forensic evidence package, is not digitally signed, and acceptance by law
enforcement or courts is not guaranteed. Preserve original devices and follow
the receiving agency's instructions.

### NOT a replacement for professional support

If the agent flags imminent self-harm or suicide risk, the **first** thing to do is reach out to the child. The **second** thing is to consult a mental-health professional. The dashboard's response card for self-harm alerts surfaces hotline numbers (US: 988 Suicide & Crisis Lifeline; localized lines for other countries) — do not rely solely on software-detected signals; talk to your kid.

## Defenses we have

| Defense | What it does | What it doesn't |
|---|---|---|
| Administrator-controlled uninstall | Relies on Windows administrator/UAC permissions | An admin can remove or disable it |
| Restricted service ACL | Non-admin can't `sc stop` the service | Admin can |
| Watchdog process pair | One restarts the other if killed | Kernel-mode killer would defeat both |
| Encrypted evidence | Screenshot/text blobs are opaque without the server key | Metadata remains in SQLite; evidence decryption requires the server's master key file. The recovery code resets dashboard access only and does not reconstruct the evidence key. |

The full threat model is in [THREAT_MODEL.md](THREAT_MODEL.md).

## False positives are expected

The LLM is not perfect. A "free Robux" joke will sometimes flag as a scam. A history class discussion of WWII may flag weapons content. A teen's poetry might flag self-harm.

- The dashboard's **False positive** button retrains nothing — it just marks the alert and helps you track patterns.
- Patterns of false positives in a category are reviewable on the dashboard.
- Tuning is in the policies (per-app sensitivity, age-group weighting).

We err **toward false positives in the critical-and-high tiers**. A missed grooming event is worse than a missed Robux-joke alert.

## False negatives are also expected

No detection system catches everything. Coded language, novel scam variants, and content that never renders on the monitored PC will slip past. GuardianNode only sees what is on screen on the monitored device — it does not see phone-only apps (Snapchat, most ephemeral platforms) or sessions on another device.

This is why GuardianNode is one tool, not the whole answer.

## When to call professional help

If GuardianNode flags any of:
- Imminent self-harm or suicide ideation
- Credible threats of violence
- Sexual exploitation or grooming
- A child sharing home address/school with an unknown adult
- A meeting being arranged off-platform with an unknown adult

…the dashboard tells you to contact help immediately. **Software detection is a head start, not a substitute.** Hotlines are localized in the alert detail page.

## Reporting harm we missed

If your child experienced online harm that GuardianNode didn't catch (or that GuardianNode caught too late), please tell us via the `safety_concern` issue template (with no PII about your child or the perpetrator). We use these reports to improve the rules and prompts. Reporting helps the next family.
