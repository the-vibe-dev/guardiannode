# Codex Computer Prompt for Video Production

Use this prompt in the Codex computer session after the exact submission commit
is checked out and the local preflight passes.

```text
Produce a 16:9, 1920x1080 GuardianNode Build Week demonstration video from the
functional local application. Target 2:48 and never exceed 2:50. Use the
repository files docs/build-week/video/SHOT_MANIFEST.json,
docs/build-week/video/VOICEOVER.txt, docs/build-week/video/CAPTIONS.srt, and
docs/build-week/VIDEO_SCRIPT.md as the authoritative plan.

Safety constraints:
- Use only the disposable mock-mode server started by
  scripts/start_build_week_video_demo.py.
- Never open an existing GuardianNode data directory.
- Do not display or narrate setup tokens, passwords, API keys, browser account
  details, private email, internal IP addresses, hostnames, notifications,
  bookmarks, or terminal history.
- Use only scenarios visibly labeled synthetic. Do not use real child or family
  data.
- Do not open developer tools or browser logs while recording.
- Do not claim zero retention, diagnosis, truth determination, emergency
  response, universal accuracy, or that the whole platform was built during
  Build Week.
- Clearly label the pre-existing platform and the Guardian Review Build Week
  extension.
- State that the recorded assessment uses deterministic mock mode. Explain that
  configured live mode uses the server-side OpenAI Responses API with GPT-5.6,
  strict output, no tools, and store:false.

Workflow:
1. Complete setup and sign-in off camera. Close unrelated applications and
   notifications. Confirm the browser contains only synthetic content.
2. Rehearse every shot once and verify all controls work. Reset the synthetic
   demo before recording.
3. Record the eight shots in SHOT_MANIFEST.json. Keep UI text readable and use
   gentle cuts; do not fabricate interface states.
4. Record clear voiceover from VOICEOVER.txt. Music is optional and must never
   carry the explanation.
5. Add the supplied SRT captions and the required disclosure overlays. Avoid
   overlays that cover UI controls or evidence.
6. Export MP4/H.264 with AAC audio. Verify duration, audio, captions, disclosure
   language, and absence of private information by watching the export from
   beginning to end.
7. Save the final file and a SHA-256 checksum outside the Git repository. Stop
   before uploading unless the maintainer explicitly authorizes the YouTube
   action in this session.
8. If upload is authorized, set visibility to Public, then verify the URL in a
   signed-out/private browser window. Record only the public URL and final
   repository commit in the maintainer's private submission notes.

If the functional UI disagrees with the script, stop and report the discrepancy.
Do not simulate, mock up, or edit around a broken golden-path control.
```
