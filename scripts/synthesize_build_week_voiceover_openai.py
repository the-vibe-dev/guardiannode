#!/usr/bin/env python3
"""Generate the Build Week narration with OpenAI's text-to-speech API."""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path


def script_body(path: Path) -> str:
    lines = path.read_text("utf-8").splitlines()
    kept = [
        line
        for line in lines
        if not line.startswith("GuardianNode — Guardian Review")
        and not re.fullmatch(r"\[\d:\d\d–\d:\d\d\]", line)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def load_key(path: Path) -> str:
    value = path.read_text("utf-8").strip()
    if "=" in value and not value.startswith("sk-"):
        value = value.split("=", 1)[1].strip().strip("\"'")
    if not value.startswith("sk-"):
        raise SystemExit("The private key file does not contain an OpenAI API key")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--api-key-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--voice", default="coral")
    args = parser.parse_args()

    payload = {
        "model": "gpt-4o-mini-tts",
        "voice": args.voice,
        "input": script_body(args.script),
        "instructions": (
            "Use a warm, confident, natural documentary narration voice. Speak in first person as the "
            "product creator. Sound thoughtful and conversational, never like an advertisement or a robot. "
            "Use clear emphasis for GuardianNode, Guardian Review, Codex, GPT-5.6, local detection, privacy, "
            "and the parent decision boundary. Keep a steady brisk pace suitable for a two-minute-forty-eight-"
            "second technical demo. Add a short natural pause between paragraphs."
        ),
        "response_format": "wav",
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_key(args.api_key_file)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"OpenAI TTS request failed with HTTP {error.code}") from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(audio)
    print(json.dumps({"status": "created", "model": payload["model"], "voice": args.voice, "bytes": len(audio)}))


if __name__ == "__main__":
    main()
