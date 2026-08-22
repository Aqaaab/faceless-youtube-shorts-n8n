#!/usr/bin/env bash
# ===========================================================================
# produce.sh — Arabic YouTube Shorts media engine
#
# Input:
#   <RUN_DIR>/job.json
#
# Expected:
#   {
#     "script": "...",
#     "query": "space",
#     "queries": ["space", "stars", "galaxy"],
#     "voice": "ar_JO-kareem-medium"
#   }
#
# Pipeline:
#   Gemini script
#        ↓
#   Piper Arabic TTS
#        ↓
#   Multiple Pexels portrait clips
#        ↓
#   FFmpeg 9:16 + Arabic captions + voice
#        ↓
#   video.mp4
# ===========================================================================

set -euo pipefail

RUN_DIR="${1:?Usage: produce.sh <RUN_DIR>}"
JOB="$RUN_DIR/job.json"

[ -s "$JOB" ] || {
  echo "ERROR: $JOB missing" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_TEXT="$(jq -r '.script // ""' "$JOB")"
QUERY="$(jq -r '.query // "nature"' "$JOB")"

VOICE="$(jq -r '.voice // "ar_JO-kareem-medium"' "$JOB")"

PEXELS_KEY="${PEXELS_API_KEY:-}"

OUT="$RUN_DIR/video.mp4"
VOICE_WAV="$RUN_DIR/voice.wav"
SUBS="$RUN_DIR/subs.srt"

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

[ -n "$SCRIPT_TEXT" ] || {
  echo "ERROR: script is empty" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# 1) Install Piper if necessary
# ---------------------------------------------------------------------------

echo "Installing/checking Piper TTS..."

python3 -m pip install --quiet --upgrade piper-tts

# ---------------------------------------------------------------------------
# 2) Prepare Piper voice
#
# The official Piper Arabic Kareem medium model is:
# ar_JO-kareem-medium
#
# Both .onnx and .onnx.json are required.
# ---------------------------------------------------------------------------

PIPER_DIR="$RUN_DIR/piper"
mkdir -p "$PIPER_DIR"

MODEL="$PIPER_DIR/ar_JO-kareem-medium.onnx"
MODEL_JSON="$PIPER_DIR/ar_JO-kareem-medium.onnx.json"

MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx?download=true"
MODEL_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json?download=true"

if [ ! -s "$MODEL" ]; then
  echo "Downloading Arabic Piper voice..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 300 \
    "$MODEL_URL" \
    -o "$MODEL"
fi

if [ ! -s "$MODEL_JSON" ]; then
  echo "Downloading Piper voice configuration..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 60 \
    "$MODEL_JSON_URL" \
    -o "$MODEL_JSON"
fi

[ -s "$MODEL" ] || {
  echo "ERROR: Piper model download failed." >&2
  exit 1
}

[ -s "$MODEL_JSON" ] || {
  echo "ERROR: Piper model configuration download failed." >&2
  exit 1
}

echo "Piper Arabic model ready."

# ---------------------------------------------------------------------------
# 3) Generate Arabic voice
# ---------------------------------------------------------------------------

printf '%s\n' "$SCRIPT_TEXT" > "$RUN_DIR/script.txt"

echo "Generating Arabic voice..."

python3 -m piper \
  --model "$MODEL" \
  --output_file "$VOICE_WAV" \
  --sentence-silence 0.12 \
  < "$RUN_DIR/script.txt"

[ -s "$VOICE_WAV" ] || {
  echo "ERROR: Piper failed to generate voice." >&2
  exit 1
}

echo "Arabic voice generated successfully."

# ---------------------------------------------------------------------------
# 4) Get voice duration
# ---------------------------------------------------------------------------

DUR="$(ffprobe \
  -v error \
  -show_entries format=duration \
  -of csv=p=0 \
  "$VOICE_WAV")"

DUR_INT="$(awk "BEGIN {print int($DUR + 0.999)}")"

echo "Voice duration: ${DUR}s"

# ---------------------------------------------------------------------------
# 5) Build list of Pexels queries
# ---------------------------------------------------------------------------

mapfile -t QUERIES < <(
  jq -r '
    if (.queries | type) == "array" and (.queries | length) > 0
    then .queries[]
    else .query // "nature"
    end
  ' "$JOB"
)

if [ "${#QUERIES[@]}" -eq 0 ]; then
  QUERIES=("$QUERY")
fi

echo "Pexels queries:"
printf ' - %s\n' "${QUERIES[@]}"

# ---------------------------------------------------------------------------
# 6) Download multiple Pexels portrait clips
# ---------------------------------------------------------------------------

PARTS=()
INDEX=0

for Q in "${QUERIES[@]}"; do

  [ -n "$Q" ] || continue

  echo "Searching Pexels: $Q"

  ENC_QUERY="$(printf '%s' "$Q" | jq -sRr @uri)"

  LINKS="$(
    curl -fsS \
      --retry 2 \
      --max-time 30 \
      -H "Authorization: $PEXELS_KEY" \
      "https://api.pexels.com/videos/search?query=${ENC_QUERY}&orientation=portrait&size=medium&per_page=15" \
      2>/dev/null |
      jq -r '
        [
          .videos[].video_files[]
          | select(
              (.height // 0) >= 720
              and (.width // 0) > 0
              and (.link // "") != ""
            )
          | .link
        ]
        | unique[]
      ' 2>/dev/null || true
  )"

  if [ -z "$LINKS" ]; then
    echo "INFO: no Pexels result for '$Q'" >&2
    continue
  fi

  PICK="$(printf '%s\n' "$LINKS" | sed -n "$((INDEX + 1))p")"

  if [ -z "$PICK" ]; then
    PICK="$(printf '%s\n' "$LINKS" | head -n 1)"
  fi

  RAW="$RUN_DIR/raw_${INDEX}.mp4"
  PART="$RUN_DIR/part_${INDEX}.mp4"

  echo "Downloading clip $INDEX..."

  if ! curl -fL \
      --retry 2 \
      --max-time 120 \
      "$PICK" \
      -o "$RAW"; then

    echo "INFO: failed downloading clip for '$Q'" >&2
    continue
  fi

  # Normalize each clip.
  # We deliberately DO NOT use -an here as the final audio is Piper.
  if ffmpeg -y \
      -hide_banner \
      -loglevel error \
      -stream_loop -1 \
      -i "$RAW" \
      -t 8 \
      -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" \
      -an \
      -c:v libx264 \
      -preset veryfast \
      -crf 23 \
      "$PART"; then

    PARTS+=("$PART")
    INDEX=$((INDEX + 1))

  else

    echo "INFO: FFmpeg normalization failed for '$Q'" >&2

  fi

  # Maximum 6 clips.
  if [ "${#PARTS[@]}" -ge 6 ]; then
    break
  fi

done

# ---------------------------------------------------------------------------
# 7) Fallback if Pexels returned too few clips
# ---------------------------------------------------------------------------

if [ "${#PARTS[@]}" -eq 0 ]; then

  echo "WARNING: No usable Pexels clips found."
  echo "Creating animated fallback background."

  FALLBACK="$RUN_DIR/fallback.mp4"

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -f lavfi \
    -i "testsrc2=size=1080x1920:rate=30" \
    -t "$DUR_INT" \
    -pix_fmt yuv420p \
    -c:v libx264 \
    -preset veryfast \
    -crf 25 \
    "$FALLBACK"

  PARTS+=("$FALLBACK")

fi

# ---------------------------------------------------------------------------
# 8) Concatenate clips
# ---------------------------------------------------------------------------

LIST="$RUN_DIR/list.txt"
CONCAT="$RUN_DIR/concat.mp4"

: > "$LIST"

for PART in "${PARTS[@]}"; do
  printf "file '%s'\n" "$PART" >> "$LIST"
done

echo "Combining ${#PARTS[@]} video clips..."

ffmpeg -y \
  -hide_banner \
  -loglevel error \
  -f concat \
  -safe 0 \
  -i "$LIST" \
  -c:v libx264 \
  -preset veryfast \
  -crf 23 \
  -pix_fmt yuv420p \
  "$CONCAT"

[ -s "$CONCAT" ] || {
  echo "ERROR: video concatenation failed." >&2
  exit 1
}

# ---------------------------------------------------------------------------
# 9) Generate Arabic subtitle file
#
# For reliability we create readable Arabic captions based on the script.
# The audio remains the authoritative duration.
# ---------------------------------------------------------------------------

python3 - "$SCRIPT_TEXT" "$SUBS" "$DUR" <<'PY'
import sys
import textwrap

script = sys.argv[1]
out = sys.argv[2]
duration = float(sys.argv[3])

# Split into short caption chunks.
words = script.split()

if not words:
    raise SystemExit("No script words")

# About 7 words per caption.
chunks = [
    " ".join(words[i:i+7])
    for i in range(0, len(words), 7)
]

chunk_duration = duration / len(chunks)

def timestamp(seconds):
    ms = int(round(seconds * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

with open(out, "w", encoding="utf-8") as f:

    for i, chunk in enumerate(chunks, 1):

        start = i - 1
        end = min(i * chunk_duration, duration)

        # Wrap long lines.
        wrapped = "\n".join(
            textwrap.wrap(
                chunk,
                width=30,
                break_long_words=False,
                break_on_hyphens=False
            )
        )

        f.write(f"{i}\n")
        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )
        f.write(wrapped + "\n\n")
PY

# ---------------------------------------------------------------------------
# 10) Final composition
# ---------------------------------------------------------------------------

echo "Rendering final Arabic Short..."

CAPTION_STYLE="FontName=DejaVu Sans,Fontsize=18,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=330"

ffmpeg -y \
  -hide_banner \
  -loglevel error \
  -stream_loop -1 \
  -i "$CONCAT" \
  -i "$VOICE_WAV" \
  -t "$DUR" \
  -filter_complex "\
[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,eq=brightness=-0.04,fps=30[bg];\
[bg]subtitles='${SUBS}':force_style='${CAPTION_STYLE}'[v]" \
  -map "[v]" \
  -map 1:a \
  -c:v libx264 \
  -preset veryfast \
  -crf 23 \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -ar 44100 \
  -ac 2 \
  -movflags +faststart \
  -shortest \
  "$OUT"

# ---------------------------------------------------------------------------
# 11) Verify final file
# ---------------------------------------------------------------------------

[ -s "$OUT" ] || {
  echo "ERROR: final video was not created." >&2
  exit 1
}

FINAL_DURATION="$(
  ffprobe \
    -v error \
    -show_entries format=duration \
    -of csv=p=0 \
    "$OUT"
)"

VIDEO_WIDTH="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries stream=width \
    -of csv=p=0 \
    "$OUT"
)"

VIDEO_HEIGHT="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries stream=height \
    -of csv=p=0 \
    "$OUT"
)"

echo "Video width: $VIDEO_WIDTH"
echo "Video height: $VIDEO_HEIGHT"
echo "Video duration: $FINAL_DURATION"
echo "Clips used: ${#PARTS[@]}"

echo \
  "{\"video\":\"${OUT}\",\"duration\":${FINAL_DURATION},\"clips\":${#PARTS[@]},\"voice\":\"ar_JO-kareem-medium\"}"
