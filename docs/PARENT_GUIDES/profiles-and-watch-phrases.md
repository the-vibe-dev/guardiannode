# Child profiles & custom watch phrases

GuardianNode can watch for the specific things that identify *your* child — their
real name, home address, school or phone number - and flag a match in captured
text that reaches the review pipeline. You set this up once in the dashboard. **You never touch
the child's PC for this.**

## 1. Create a profile for your child

1. Open the dashboard and go to **Profiles**.
2. Click **Add profile**.
3. Enter a name (e.g. "Alex") and pick the **age group** (Under 10 / 10–13 /
   14–17). The age group supplies context to the classifier; configured review
   thresholds determine which results become alerts.
4. In **Custom watch phrases**, add the personal details you want flagged, one
   per line. For example:
   - `Alex Example` (name)
   - `Family Lastname` (last name)
   - `123 Example Street` (home address — a partial like just the street counts too)
   - `Example Middle School` (school name)
   - a phone number
5. Save.

## 2. Assign the profile to the child's device

1. Go to **Devices**.
2. Find the child's PC in the list.
3. In the **Child** column, pick the profile you just created from the dropdown.

Eligible screenshots from that device use the assigned profile. A phrase must
be visible in a sampled frame and successfully extracted or identified for it
to be matched. OCR and models can miss text.

## What happens when a phrase is seen

When the pipeline matches a configured watch phrase in captured text, it can
produce a **high-severity alert** with the category `custom_watch`, subject to
current capture and alert policy. The finding includes the matched evidence.
A visible phrase does not guarantee a capture, readable OCR or an AI match.

This can help surface possible sharing of identifying information ("what's your address?", "what school do
you go to?"). It works alongside the AI's normal grooming/self-harm/scam
detection, not instead of it.

## Tips

- **Add real, specific phrases.** Common words ("school") will over-trigger; use
  the actual school *name*. Use the full street or the full name where you can.
- **Multi-word phrases** match as a whole; **single words** match whole-word only
  (so "Alex" won't match "alexandrite").
- Matching is **case-insensitive**.
- You can edit the phrases any time in **Profiles** — changes apply to new
  screenshots immediately.
- One profile can cover one device; if you have several kids/PCs, make a profile
  per child and assign each to the right device.

## Why this is on the server, not the kid's PC

The child's PC just captures the screen. *You* decide — from your dashboard —
which child a device belongs to and what to watch for. The kid never sees the
watch list, and you don't have to reconfigure their machine to change it.

Watch phrases influence review and alerts. They never block a website, close an
app or limit time spent on the device.
