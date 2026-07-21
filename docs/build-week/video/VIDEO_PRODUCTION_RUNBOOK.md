# Video Production Runbook

This package prepares the functional demonstration for Codex computer. It does
not publish a video or claim that YouTube verification has happened.

## 1. Freeze and preflight

Check out the exact submitted tag or commit. From the repository root, run:

```bash
python scripts/check_build_week_submission.py
python scripts/check_version_consistency.py
cd backend && python -m pytest -q tests ../tests/e2e && cd ..
cd dashboard && npm test -- --run && npm run typecheck && npm run build && cd ..
```

Optionally recapture the five synthetic proof screenshots. This runs the real
browser flow against a disposable backend and requires Selenium, Chromium, and
Chromedriver:

```bash
python scripts/capture_build_week_screenshots.py \
  --output-dir local_config/video-preflight-screenshots
```

Never point these helpers at a real GuardianNode data directory.

## 2. Start the disposable recording server

Use the Python environment where backend development dependencies are installed:

```bash
python scripts/start_build_week_video_demo.py --open-browser
```

The helper explicitly removes OpenAI keys from its child environment, binds to
loopback, enables only synthetic demo mode, and selects the local deterministic
mock provider. It prints the path to the one-time setup token file but never
prints the token. Complete setup and sign-in before recording. Use a manufactured
parent name and password; do not reuse a real credential.

## 3. Prepare the desktop

- Use a clean browser profile with no bookmarks, extensions, autofill, or
  account avatar.
- Disable notifications and hide the taskbar if it contains identifying apps.
- Use 100% browser zoom at 1920x1080; confirm all required content is legible.
- Close terminals after setup. Never record a setup token, password, key, local
  path, private hostname, internal address, or browser console.
- Use scenario **Unknown contact requesting secrecy and platform migration**.
- Reset the scenario and leave the browser on **Synthetic demo** before take 1.

## 4. Record and assemble

Follow `SHOT_MANIFEST.json` and `VOICEOVER.txt`. The eight shot windows total
2:48. The dashboard recording must visibly show local creation, an exact
outbound preview, explicit approval, structured guidance, the parent decision
boundary, and feedback. Show the repository baseline/evaluation only from clean
rendered pages—not terminal history.

Use the supplied `CAPTIONS.srt`. The produced submission asset is MP4/H.264 with
AAC audio and embedded English captions at 1280x720. Its Coral narration was
generated with OpenAI `gpt-4o-mini-tts` and is disclosed on the title card. Do
not stretch still images to imply a control worked; the source UI must be
functional in the take.

## 5. Final watch-through

- Duration is 2:35–2:50 and voiceover is intelligible.
- The recording accurately shows a live GPT-5.6 request using only minimized
  synthetic content; it does not claim account-wide zero retention.
- Existing platform and Build Week extension disclosures are visible.
- No unsupported safety, diagnostic, truth, retention, or authorship claim is
  present.
- No personal/confidential content appears in video, audio, captions, file name,
  or metadata.
- The final frame shows `https://github.com/the-vibe-dev/guardiannode`.

Generate a checksum outside the repository:

```bash
sha256sum GuardianNode-Guardian-Review-Build-Week.mp4
```

On PowerShell:

```powershell
Get-FileHash .\GuardianNode-Guardian-Review-Build-Week.mp4 -Algorithm SHA256
```

If `ffprobe` is installed, the repository helper checks both the required
duration window and SHA-256 in one read-only command:

```bash
python scripts/check_build_week_video.py \
  /path/to/GuardianNode-Guardian-Review-Build-Week-2026.mp4
```

## Produced asset (2026-07-21)

- File: `GuardianNode-Guardian-Review-Build-Week-2026.mp4`
- Duration: 168.000 seconds
- Video/audio/subtitles: H.264 1280x720 / AAC / embedded English `mov_text`
- Narration: OpenAI `gpt-4o-mini-tts`, Coral voice; AI-generated disclosure shown
- SHA-256: `649e01da5944f193a8801d09dfed3001d0526ddd14fc8d53c8db49ca420b55de`
- Private handoff: Windows qualification desktop and NAS submission drop point

The maintainer must still upload the file, set YouTube visibility to Public,
listen through the uploaded version, and verify it while signed out.

## 6. Upload gate

Use the reviewed title, description, thumbnail guidance, and settings in
[`YOUTUBE_COPY.md`](YOUTUBE_COPY.md). Upload only after the final watch-through.
Set YouTube visibility to **Public**,
open the resulting URL in a signed-out/private browser window, and verify video,
audio, captions, title, and description. Save the URL, checksum, duration, upload
timestamp, and verification result in the private submission record. Do not
commit account screenshots, a Codex Session ID, or form confirmation containing
private data.
