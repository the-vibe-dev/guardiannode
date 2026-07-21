#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 ASSET_DIR VOICEOVER_WAV OUTPUT_MP4" >&2
  exit 2
fi

assets=$(realpath "$1")
voiceover=$(realpath "$2")
output=$(realpath -m "$3")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
captions="$repo_root/docs/build-week/video/CAPTIONS.srt"
font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
bold="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

required=(
  01-installed-demo-ready.png
  01-live-client-server-alert.png
  03-live-agent-capture.png
  04-live-exact-outbound-preview.png
  05-live-review-running.png
  06-live-structured-result.png
)
for name in "${required[@]}"; do
  [[ -f "$assets/$name" ]] || { echo "missing asset: $name" >&2; exit 2; }
done
[[ -f "$voiceover" ]] || { echo "missing voiceover: $voiceover" >&2; exit 2; }
[[ -f "$captions" ]] || { echo "missing captions: $captions" >&2; exit 2; }

convert "$assets/04-live-exact-outbound-preview.png" -crop 1424x900+0+900 +repage "$work/preview.png"
convert "$assets/06-live-structured-result.png" -crop 1424x900+0+1800 +repage "$work/result-assessment.png"
convert "$assets/06-live-structured-result.png" -crop 1424x900+0+3000 +repage "$work/result-conversation.png"
convert "$assets/06-live-structured-result.png" -crop 1424x900+0+4800 +repage "$work/result-feedback.png"

still() {
  local input=$1 duration=$2 filter=$3 destination=$4
  ffmpeg -hide_banner -loglevel error -y -loop 1 -i "$input" -t "$duration" \
    -vf "$filter,fps=24,format=yuv420p" -an -c:v libx264 -preset ultrafast -crf 20 -f mpegts "$destination"
}

card() {
  local duration=$1 filter=$2 destination=$3
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "color=c=0x0b3b49:s=1280x720:r=24:d=$duration" \
    -vf "$filter,format=yuv420p" -an -c:v libx264 -preset ultrafast -crf 20 -f mpegts "$destination"
}

card 20 \
  "drawbox=x=0:y=0:w=1280:h=10:color=0x52c7b8:t=fill,drawtext=fontfile=$bold:text='GuardianNode':fontsize=58:fontcolor=white:x=95:y=145,drawtext=fontfile=$bold:text='Guardian Review':fontsize=44:fontcolor=0x91e8dc:x=95:y=235,drawtext=fontfile=$font:text='Local detection. Parent-controlled context. Practical conversation guidance.':fontsize=22:fontcolor=white:x=98:y=330,drawtext=fontfile=$bold:text='SYNTHETIC DEMONSTRATION — NO REAL FAMILY DATA':fontsize=18:fontcolor=0xffd166:x=98:y=410,drawtext=fontfile=$font:text='Narration is an AI-generated OpenAI voice.':fontsize=17:fontcolor=white:x=98:y=490,drawtext=fontfile=$font:text='Apps for Your Life · Build Week 2026':fontsize=19:fontcolor=0xc7d9df:x=98:y=540" \
  "$work/01-title.ts"

still "$assets/01-installed-demo-ready.png" 20 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=60:color=0x0b3b49@0.95:t=fill,drawtext=fontfile=$bold:text='Existing before Build Week':fontsize=26:fontcolor=white:x=42:y=16,drawtext=fontfile=$font:text='Windows agent · backend · local detection · encrypted evidence · dashboard · installers':fontsize=16:fontcolor=0xd8f3ef:x=380:y=21" \
  "$work/02-existing.ts"

still "$assets/01-live-client-server-alert.png" 12 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='REAL CLIENT → SERVER ALERT':fontsize=23:fontcolor=white:x=38:y=14,drawtext=fontfile=$font:text='Mild synthetic gaming fixture · local rules-only detection':fontsize=16:fontcolor=0xffd166:x=470:y=18" \
  "$work/03-alert.ts"

still "$assets/03-live-agent-capture.png" 13 \
  "scale=1280:-1,crop=1280:720:0:175,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='ENCRYPTED AGENT CAPTURE + LOCAL OCR':fontsize=21:fontcolor=white:x=38:y=15,drawtext=fontfile=$font:text='Synthetic fixture · audited evidence view':fontsize=16:fontcolor=0xffd166:x=770:y=18" \
  "$work/04-capture.ts"

still "$work/preview.png" 23 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='EXACT OUTBOUND PREVIEW':fontsize=23:fontcolor=white:x=38:y=14,drawtext=fontfile=$font:text='Parent sees minimized JSON before live OpenAI processing':fontsize=16:fontcolor=0xffd166:x=485:y=18" \
  "$work/05-preview.ts"

still "$assets/05-live-review-running.png" 17 \
  "scale=1280:-1,crop=1280:720:0:920,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='LIVE GPT-5.6 GUARDIAN REVIEW':fontsize=23:fontcolor=white:x=38:y=14,drawtext=fontfile=$font:text='Responses API · no tools · store=false · strict schema':fontsize=16:fontcolor=0xffd166:x=620:y=18" \
  "$work/06-running.ts"

still "$work/result-assessment.png" 8 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='STRICT STRUCTURED ASSESSMENT':fontsize=22:fontcolor=white:x=38:y=15,drawtext=fontfile=$font:text='Ambiguous · medium · facts separated from inference':fontsize=16:fontcolor=0xffd166:x=600:y=18" \
  "$work/07a-assessment.ts"

still "$work/result-conversation.png" 9 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='PARENT COMMUNICATION PLAN':fontsize=22:fontcolor=white:x=38:y=15,drawtext=fontfile=$font:text='Calm tone · suggested opening · questions · phrases to avoid':fontsize=16:fontcolor=0xffd166:x=555:y=18" \
  "$work/07b-conversation.ts"

still "$work/result-feedback.png" 8 \
  "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f7fa,drawbox=x=0:y=0:w=1280:h=54:color=0x0b3b49@0.94:t=fill,drawtext=fontfile=$bold:text='LIMITATIONS + LOCAL PARENT FEEDBACK':fontsize=22:fontcolor=white:x=38:y=15,drawtext=fontfile=$font:text='Human decision boundary remains visible':fontsize=16:fontcolor=0xffd166:x=790:y=18" \
  "$work/07c-feedback.ts"

card 25 \
  "drawbox=x=0:y=0:w=1280:h=10:color=0x52c7b8:t=fill,drawtext=fontfile=$bold:text='How I used Codex + GPT-5.6':fontsize=45:fontcolor=white:x=88:y=95,drawtext=fontfile=$font:text='Preserved the baseline and traced the real agent-to-dashboard path':fontsize=21:fontcolor=0xd8f3ef:x=92:y=205,drawtext=fontfile=$font:text='Implemented schema · redaction · consent · persistence · UI · recovery':fontsize=21:fontcolor=0xd8f3ef:x=92:y=255,drawtext=fontfile=$font:text='Built 55 synthetic evaluation cases and adversarial checks':fontsize=21:fontcolor=0xd8f3ef:x=92:y=305,drawtext=fontfile=$font:text='Runtime — tool-free Responses API with a strict versioned output contract':fontsize=21:fontcolor=0xd8f3ef:x=92:y=355,drawtext=fontfile=$bold:text='Guardian Review added during Build Week':fontsize=25:fontcolor=0xffd166:x=92:y=455,drawtext=fontfile=$font:text='Pre-existing UI portions were Claude-assisted; disclosed in the repository.':fontsize=17:fontcolor=white:x=92:y=510" \
  "$work/08-codex.ts"

card 13 \
  "drawbox=x=0:y=0:w=1280:h=10:color=0x52c7b8:t=fill,drawtext=fontfile=$bold:text='The parent remains the decision-maker.':fontsize=39:fontcolor=white:x=88:y=155,drawtext=fontfile=$font:text='Alpha second opinion — not diagnosis, emergency service, truth detector, or punishment engine.':fontsize=20:fontcolor=0xd8f3ef:x=92:y=260,drawtext=fontfile=$bold:text='github.com/the-vibe-dev/guardiannode':fontsize=24:fontcolor=0xffd166:x=92:y=375,drawtext=fontfile=$font:text='GuardianNode · Apps for Your Life · Build Week 2026':fontsize=19:fontcolor=white:x=92:y=430" \
  "$work/09-close.ts"

ffmpeg -hide_banner -loglevel error -y \
  -i "concat:$work/01-title.ts|$work/02-existing.ts|$work/03-alert.ts|$work/04-capture.ts|$work/05-preview.ts|$work/06-running.ts|$work/07a-assessment.ts|$work/07b-conversation.ts|$work/07c-feedback.ts|$work/08-codex.ts|$work/09-close.ts" \
  -c copy "$work/visual.mp4"
mkdir -p "$(dirname "$output")"
ffmpeg -hide_banner -loglevel error -y \
  -i "$work/visual.mp4" -i "$voiceover" -i "$captions" \
  -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11,apad" -t 168 \
  -map 0:v:0 -map 1:a:0 -map 2:s:0 \
  -c:v copy -c:a aac -b:a 192k -c:s mov_text \
  -metadata title="GuardianNode — Guardian Review | Build Week 2026" \
  -metadata comment="Synthetic demonstration; live GPT-5.6 Guardian Review; no real family data" \
  -metadata:s:s:0 language=eng -movflags +faststart "$output"

ffmpeg -hide_banner -loglevel error -y -ss 5 -i "$output" -frames:v 1 "${output%.mp4}-thumbnail.png"
echo "$output"
