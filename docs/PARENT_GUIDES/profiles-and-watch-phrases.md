# Child profiles & custom watch phrases

GuardianNode can watch for the specific things that identify *your* child — their
real name, home address, school, phone number — and alert you the moment any of
them shows up on screen. You set this up once in the dashboard. **You never touch
the child's PC for this.**

## 1. Create a profile for your child

1. Open the dashboard and go to **Profiles**.
2. Click **Add profile**.
3. Enter a name (e.g. "Kale") and pick the **age group** (Under 10 / 10–13 /
   14–17). The age group tunes how sensitive detection is — younger ages flag
   more aggressively.
4. In **Custom watch phrases**, add the personal details you want flagged, one
   per line. For example:
   - `Kale` (first name)
   - `Vosburgh` (last name)
   - `3253 Oak Dr` (home address — a partial like just the street counts too)
   - `Charter School` (school name)
   - a phone number
5. Save.

## 2. Assign the profile to the child's device

1. Go to **Devices**.
2. Find the child's PC in the list.
3. In the **Child** column, pick the profile you just created from the dropdown.

That's it. From now on, every screenshot from that device is checked against the
profile's watch phrases.

## What happens when a phrase is seen

If any watch phrase appears on screen — typed in a Discord chat, pasted into a
document, or even printed inside an image (like a photo of a school ID) — you get
a **high-severity alert** in the Risk Feed with the category `custom_watch`. The
alert quotes where it was seen.

This is the single most useful signal for catching a child sharing identifying
information with someone they met online ("what's your address?", "what school do
you go to?"). It works alongside the AI's normal grooming/self-harm/scam
detection, not instead of it.

## Tips

- **Add real, specific phrases.** Common words ("school") will over-trigger; use
  the actual school *name*. Use the full street or the full name where you can.
- **Multi-word phrases** match as a whole; **single words** match whole-word only
  (so "Kale" won't match "kaleidoscope").
- Matching is **case-insensitive**.
- You can edit the phrases any time in **Profiles** — changes apply to new
  screenshots immediately.
- One profile can cover one device; if you have several kids/PCs, make a profile
  per child and assign each to the right device.

## Why this is on the server, not the kid's PC

The child's PC just captures the screen. *You* decide — from your dashboard —
which child a device belongs to and what to watch for. The kid never sees the
watch list, and you don't have to reconfigure their machine to change it.
