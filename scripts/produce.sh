#!/usr/bin/env bash
# ===========================================================================
# produce.sh — Arabic YouTube Shorts scene-based media engine
#
# Input:
#   <RUN_DIR>/job.json
#
# Expected:
# {
#   "script": "...",
#   "voice": "ar_JO-kareem-medium",
#   "scenes": [
#     {
#       "text": "نص المشهد...",
#       "pexels_query": "octopus ocean"
#     },
#     {
#       "text": "نص المشهد...",
#       "pexels_query": "octopus swimming"
#     }
#   ]
# }
#
# Pipeline:
#
# Gemini
#    ↓
# Scene 1 ──→ Piper voice ──→ Pexels clip
# Scene 2 ──→ Piper voice ──→ Pexels clip
# Scene 3 ──→ Piper voice ──→ Pexels clip
# ...
#    ↓
# Each video duration follows its own voice duration
#    ↓
# Animated crop + captions
#    ↓
# Final 1080x1920 Short
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

PEXELS_KEY="${PEXELS_API_KEY:-}"

VOICE="$(jq -r '.voice // "ar_JO-kareem-medium"' "$JOB")"

OUT="$RUN_DIR/video.mp4"

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

PIPER_DIR="$RUN_DIR/piper"

SCENES_DIR="$RUN_DIR/scenes"
AUDIO_DIR="$SCENES_DIR/audio"
VIDEO_DIR="$SCENES_DIR/video"
RAW_DIR="$SCENES_DIR/raw"

mkdir -p \
  "$PIPER_DIR" \
  "$SCENES_DIR" \
  "$AUDIO_DIR" \
  "$VIDEO_DIR" \
  "$RAW_DIR"

# ---------------------------------------------------------------------------
# Validate scenes
# ---------------------------------------------------------------------------

SCENE_COUNT="$(
  jq -r '
    if (.scenes | type) == "array"
    then (.scenes | length)
    else 0
    end
  ' "$JOB"
)"

if [ "$SCENE_COUNT" -lt 4 ]; then
  echo "ERROR: job.json must contain at least 4 scenes." >&2
  exit 1
fi

echo "=============================================="
echo "Arabic Shorts Scene Engine"
echo "Scenes: $SCENE_COUNT"
echo "Voice: $VOICE"
echo "=============================================="

# ---------------------------------------------------------------------------
# Install Piper
# ---------------------------------------------------------------------------

echo "Checking Piper..."

python3 -m pip install \
  --quiet \
  --upgrade \
  piper-tts

# ---------------------------------------------------------------------------
# Download Arabic Kareem model
# ---------------------------------------------------------------------------

MODEL="$PIPER_DIR/ar_JO-kareem-medium.onnx"
MODEL_JSON="$PIPER_DIR/ar_JO-kareem-medium.onnx.json"

MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx?download=true"

MODEL_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json?download=true"

if [ ! -s "$MODEL" ]; then

  echo "Downloading Arabic Piper model..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 300 \
    "$MODEL_URL" \
    -o "$MODEL"

fi

if [ ! -s "$MODEL_JSON" ]; then

  echo "Downloading Piper configuration..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 60 \
    "$MODEL_JSON_URL" \
    -o "$MODEL_JSON"

fi

[ -s "$MODEL" ] || {
  echo "ERROR: Piper model missing." >&2
  exit 1
}

[ -s "$MODEL_JSON" ] || {
  echo "ERROR: Piper model configuration missing." >&2
  exit 1
}

echo "Piper ready."

# ---------------------------------------------------------------------------
# Generate voice + video for every scene
# ---------------------------------------------------------------------------

PARTS=()
AUDIO_PARTS=()

TOTAL_DURATION=0

for ((i=0; i<SCENE_COUNT; i++)); do

  SCENE_TEXT="$(
    jq -r \
      ".scenes[$i].text // \"\"" \
      "$JOB"
  )"

  PEXELS_QUERY="$(
    jq -r \
      ".scenes[$i].pexels_query // \"nature\"" \
      "$JOB"
  )"

  if [ -z "$SCENE_TEXT" ]; then
    echo "WARNING: Scene $((i+1)) has no text. Skipping."
    continue
  fi

  if [ -z "$PEXELS_QUERY" ]; then
    PEXELS_QUERY="nature"
  fi

  echo
  echo "=============================================="
  echo "SCENE $((i+1)) / $SCENE_COUNT"
  echo "Visual: $PEXELS_QUERY"
  echo "Text: $SCENE_TEXT"
  echo "=============================================="

  SCENE_TEXT_FILE="$SCENES_DIR/scene_${i}.txt"

  AUDIO="$AUDIO_DIR/audio_${i}.wav"

  SUB="$SCENES_DIR/sub_${i}.srt"

  RAW="$RAW_DIR/raw_${i}.mp4"

  VIDEO="$VIDEO_DIR/video_${i}.mp4"

  printf '%s\n' "$SCENE_TEXT" > "$SCENE_TEXT_FILE"

  # -------------------------------------------------------------------------
  # Generate voice specifically for this scene
  # -------------------------------------------------------------------------

  echo "Generating scene voice..."

  python3 -m piper \
    --model "$MODEL" \
    --output_file "$AUDIO" \
    --sentence-silence 0.12 \
    < "$SCENE_TEXT_FILE"

  [ -s "$AUDIO" ] || {
    echo "ERROR: Piper failed for scene $i." >&2
    exit 1
  }

  SCENE_DUR="$(
    ffprobe \
      -v error \
      -show_entries format=duration \
      -of csv=p=0 \
      "$AUDIO"
  )"

  echo "Scene voice duration: ${SCENE_DUR}s"

  # -------------------------------------------------------------------------
  # Search Pexels specifically for this scene
  # -------------------------------------------------------------------------

  VIDEO_URL=""

  if [ -n "$PEXELS_KEY" ]; then

    ENC_QUERY="$(
      printf '%s' "$PEXELS_QUERY" |
      jq -sRr @uri
    )"

    echo "Searching Pexels for: $PEXELS_QUERY"

    mapfile -t LINKS < <(

      curl -fsS \
        --retry 2 \
        --max-time 30 \
        -H "Authorization: $PEXELS_KEY" \
        "https://api.pexels.com/videos/search?query=${ENC_QUERY}&orientation=portrait&size=medium&per_page=20" \
        2>/dev/null |

      jq -r '
        [
          .videos[]
          | .video_files[]
          | select(
              (.link // "") != ""
              and (.height // 0) >= 720
          )
          | .link
        ]
        | unique[]
      ' 2>/dev/null || true

    )

    if [ "${#LINKS[@]}" -gt 0 ]; then

      # Pick different result for different scenes.
      PICK_INDEX=$((i % ${#LINKS[@]}))

      VIDEO_URL="${LINKS[$PICK_INDEX]}"

    fi

  fi

  # -------------------------------------------------------------------------
  # Download scene video
  # -------------------------------------------------------------------------

  if [ -n "$VIDEO_URL" ]; then

    echo "Downloading matching Pexels scene..."

    if ! curl -fL \
        --retry 2 \
        --max-time 120 \
        "$VIDEO_URL" \
        -o "$RAW"; then

      echo "WARNING: Pexels download failed."
      VIDEO_URL=""

    fi

  fi

  # -------------------------------------------------------------------------
  # Fallback animated background
  # -------------------------------------------------------------------------

  if [ ! -s "$RAW" ]; then

    echo "WARNING: No Pexels clip. Creating animated fallback."

    ffmpeg -y \
      -hide_banner \
      -loglevel error \
      -f lavfi \
      -i "testsrc2=size=1080x1920:rate=30" \
      -t "$SCENE_DUR" \
      -pix_fmt yuv420p \
      -c:v libx264 \
      -preset veryfast \
      -crf 25 \
      "$RAW"

  fi

  # -------------------------------------------------------------------------
  # Generate scene subtitle
  # -------------------------------------------------------------------------

  python3 - \
    "$SCENE_TEXT" \
    "$SUB" \
    "$SCENE_DUR" \
    <<'PY'

import sys
import textwrap

text = sys.argv[1]
out = sys.argv[2]
duration = float(sys.argv[3])

words = text.split()

if not words:
    raise SystemExit("Empty scene text")

# Shorter captions = easier to read on Shorts.
chunks = [
    " ".join(words[i:i+5])
    for i in range(0, len(words), 5)
]

chunk_duration = duration / len(chunks)

def timestamp(seconds):

    milliseconds = int(round(seconds * 1000))

    hours = milliseconds // 3600000

    milliseconds %= 3600000

    minutes = milliseconds // 60000

    milliseconds %= 60000

    seconds_value = milliseconds // 1000

    milliseconds %= 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds_value:02d},"
        f"{milliseconds:03d}"
    )

with open(
    out,
    "w",
    encoding="utf-8"
) as f:

    for index, chunk in enumerate(
        chunks,
        1
    ):

        start = (
            index - 1
        ) * chunk_duration

        end = min(
            index * chunk_duration,
            duration
        )

        wrapped = "\n".join(
            textwrap.wrap(
                chunk,
                width=26,
                break_long_words=False,
                break_on_hyphens=False
            )
        )

        f.write(
            f"{index}\n"
        )

        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )

        f.write(
            wrapped +
            "\n\n"
        )

PY

  # -------------------------------------------------------------------------
  # Render individual scene
  #
  # Important:
  # The scene duration is controlled by its own voice.
  #
  # This prevents the old problem where one video clip keeps looping
  # while unrelated narration continues.
  # -------------------------------------------------------------------------

  echo "Rendering scene..."

  CAPTION_STYLE="FontName=DejaVu Sans,Fontsize=19,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=320"

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -stream_loop -1 \
    -i "$RAW" \
    -i "$AUDIO" \
    -t "$SCENE_DUR" \
    -filter_complex "\
[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920:x='(in_w-out_w)/2+12*sin(t*0.35)':y='(in_h-out_h)/2+10*cos(t*0.30)',setsar=1,fps=30,eq=brightness=-0.04:saturation=1.05[v0];\
[v0]subtitles='${SUB}':force_style='${CAPTION_STYLE}'[v]" \
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
    -shortest \
    "$VIDEO"

  [ -s "$VIDEO" ] || {
    echo "ERROR: scene rendering failed." >&2
    exit 1
  }

  PARTS+=("$VIDEO")

  AUDIO_PARTS+=("$AUDIO")

  TOTAL_DURATION="$(
    awk \
      -v a="$TOTAL_DURATION" \
      -v b="$SCENE_DUR" \
      'BEGIN {printf "%.3f", a+b}'
  )"

done

# ---------------------------------------------------------------------------
# Make sure we have enough scenes
# ---------------------------------------------------------------------------

if [ "${#PARTS[@]}" -lt 4 ]; then

  echo "ERROR: fewer than 4 usable scenes." >&2

  exit 1

fi

echo
echo "=============================================="
echo "All scenes rendered."
echo "Usable scenes: ${#PARTS[@]}"
echo "Total duration: ${TOTAL_DURATION}s"
echo "=============================================="

# ---------------------------------------------------------------------------
# Concatenate rendered scenes
# ---------------------------------------------------------------------------

LIST="$RUN_DIR/final_list.txt"

FINAL="$RUN_DIR/final_video.mp4"

: > "$LIST"

for PART in "${PARTS[@]}"; do

  printf "file '%s'\n" "$PART" >> "$LIST"

done

echo "Combining scenes..."

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
  -c:a aac \
  -b:a 192k \
  -ar 44100 \
  -ac 2 \
  -movflags +faststart \
  "$FINAL"

[ -s "$FINAL" ] || {
  echo "ERROR: final video creation failed." >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Copy final output
# ---------------------------------------------------------------------------

cp "$FINAL" "$OUT"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

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

echo
echo "=============================================="
echo "FINAL VIDEO READY"
echo "=============================================="
echo "Width:    $VIDEO_WIDTH"
echo "Height:   $VIDEO_HEIGHT"
echo "Duration: $FINAL_DURATION"
echo "Scenes:   ${#PARTS[@]}"
echo "Voice:    $VOICE"
echo "=============================================="

echo \
  "{\"video\":\"${OUT}\",\"duration\":${FINAL_DURATION},\"scenes\":${#PARTS[@]},\"voice\":\"${VOICE}\"}"
