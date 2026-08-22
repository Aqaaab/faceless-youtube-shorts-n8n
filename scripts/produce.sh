#!/usr/bin/env bash
# ===========================================================================
# produce.sh
#
# YouTube Shorts Video Engine
#
# VOICE:
#   Kokoro TTS
#   Voice: af_bella
#   Language: English US
#   Speed: 1.0
#
# INPUT:
# Supports BOTH:
#
# 1) Scene format:
# {
#   "voice": "af_bella",
#   "scenes": [
#     {
#       "text_en": "...",
#       "text_ar": "...",
#       "pexels_query": "..."
#     }
#   ]
# }
#
# 2) Workflow format:
# {
#   "script": "...",
#   "query": "...",
#   "voice": "..."
# }
#
# OUTPUT:
#   $RUN_DIR/video.mp4
#
# ===========================================================================

set -euo pipefail

RUN_DIR="${1:?Usage: produce.sh <RUN_DIR>}"
JOB="$RUN_DIR/job.json"

# ===========================================================================
# 0. Validate
# ===========================================================================

if [ ! -s "$JOB" ]; then
  echo "ERROR: $JOB missing"
  exit 1
fi

echo
echo "================================================"
echo "KOKORO BELLA SHORTS ENGINE"
echo "================================================"

# ===========================================================================
# 1. Environment
# ===========================================================================

PEXELS_KEY="${PEXELS_API_KEY:-}"

# IMPORTANT:
# Always use Bella regardless of what the workflow sends.
VOICE="af_bella"

OUT="$RUN_DIR/video.mp4"

KOKORO_DIR="$RUN_DIR/kokoro"

SCENES_DIR="$RUN_DIR/scenes"
AUDIO_DIR="$SCENES_DIR/audio"
VIDEO_DIR="$SCENES_DIR/video"
RAW_DIR="$SCENES_DIR/raw"

mkdir -p \
  "$KOKORO_DIR" \
  "$SCENES_DIR" \
  "$AUDIO_DIR" \
  "$VIDEO_DIR" \
  "$RAW_DIR"

echo "Voice  : $VOICE"
echo "Speed  : 1.0"
echo "Lang   : en-us"
echo "Subs   : Arabic"
echo

# ===========================================================================
# 2. Install system dependencies
# ===========================================================================

echo "Checking system dependencies..."

if command -v apt-get >/dev/null 2>&1; then

  echo "Installing PortAudio..."

  apt-get update -qq

  apt-get install -y -qq \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1

fi

# ===========================================================================
# 3. Install Kokoro
# ===========================================================================

echo "Checking Kokoro TTS..."

python3 -m pip install \
  --quiet \
  --upgrade \
  kokoro-tts \
  sounddevice

# ===========================================================================
# 4. Kokoro model
# ===========================================================================

KOKORO_MODEL="$KOKORO_DIR/kokoro-v1.0.onnx"
KOKORO_VOICES="$KOKORO_DIR/voices-v1.0.bin"

KOKORO_MODEL_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"

KOKORO_VOICES_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"

if [ ! -s "$KOKORO_MODEL" ]; then

  echo "Downloading Kokoro model..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 600 \
    "$KOKORO_MODEL_URL" \
    -o "$KOKORO_MODEL"

fi

if [ ! -s "$KOKORO_VOICES" ]; then

  echo "Downloading Kokoro voice data..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 600 \
    "$KOKORO_VOICES_URL" \
    -o "$KOKORO_VOICES"

fi

[ -s "$KOKORO_MODEL" ] || {
  echo "ERROR: Kokoro model missing."
  exit 1
}

[ -s "$KOKORO_VOICES" ] || {
  echo "ERROR: Kokoro voices missing."
  exit 1
}

echo "Kokoro model ready."

# ===========================================================================
# 5. Locate Kokoro
# ===========================================================================

KOKORO_BIN="$(command -v kokoro-tts || true)"

if [ -z "$KOKORO_BIN" ]; then

  echo "ERROR: kokoro-tts command not found."

  exit 1

fi

echo "Kokoro executable: $KOKORO_BIN"

# ===========================================================================
# 6. Build scenes from job.json
# ===========================================================================

echo "Preparing scenes..."

SCENE_COUNT="$(
  jq -r '
    if (.scenes | type) == "array"
    then (.scenes | length)
    else 0
    end
  ' "$JOB"
)"

# ---------------------------------------------------------------------------
# If scenes[] exists, use it.
# ---------------------------------------------------------------------------

if [ "$SCENE_COUNT" -gt 0 ]; then

  echo "Detected scene-based job."

else

  # -------------------------------------------------------------------------
  # Workflow currently sends:
  #
  # {
  #   script: "...",
  #   query: "...",
  #   voice: "..."
  # }
  #
  # Convert it into scenes automatically.
  # -------------------------------------------------------------------------

  SCRIPT_TEXT="$(
    jq -r '.script // .text // ""' "$JOB"
  )"

  QUERY="$(
    jq -r '.query // "nature"' "$JOB"
  )"

  if [ -z "$SCRIPT_TEXT" ] || [ "$SCRIPT_TEXT" = "null" ]; then

    echo "ERROR: job.json contains neither scenes nor script."

    exit 1

  fi

  echo "Detected workflow job."
  echo "Converting script into scenes..."

  export SCRIPT_TEXT
  export QUERY

  python3 - "$JOB" <<'PY'

import json
import os
import re
import sys

job_file = sys.argv[1]

script = os.environ.get("SCRIPT_TEXT", "").strip()
query = os.environ.get("QUERY", "nature").strip()

# Split narration into sentences.
sentences = re.split(
    r'(?<=[.!?])\s+',
    script
)

sentences = [
    s.strip()
    for s in sentences
    if s.strip()
]

# If the script is short, keep it as one scene.
# Otherwise create approximately 5 scenes.
target = 5

if len(sentences) <= target:
    groups = sentences
else:

    groups = []

    per_group = max(
        1,
        (len(sentences) + target - 1) // target
    )

    for i in range(0, len(sentences), per_group):

        groups.append(
            " ".join(sentences[i:i + per_group])
        )

scenes = []

for text in groups:

    scenes.append({
        "text_en": text,
        "text_ar": text,
        "pexels_query": query
    })

job["voice"] = "af_bella"
job["scenes"] = scenes

# Keep the original script.
job["script"] = script

with open(job_file, "w", encoding="utf-8") as f:

    json.dump(
        job,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    f"Created {len(scenes)} scenes."
)

PY

  SCENE_COUNT="$(
    jq -r '.scenes | length' "$JOB"
  )"

fi

# ===========================================================================
# 7. Validate scene count
# ===========================================================================

if [ "$SCENE_COUNT" -lt 1 ]; then

  echo "ERROR: No scenes found."

  exit 1

fi

echo
echo "Scenes : $SCENE_COUNT"
echo "Voice  : $VOICE"
echo

# ===========================================================================
# 8. Generate scenes
# ===========================================================================

PARTS=()
TOTAL_DURATION="0"

for ((i=0; i<SCENE_COUNT; i++)); do

  # -------------------------------------------------------------------------
  # English narration
  # -------------------------------------------------------------------------

  SCENE_TEXT_EN="$(
    jq -r \
      ".scenes[$i].text_en // .scenes[$i].text // \"\"" \
      "$JOB"
  )"

  # -------------------------------------------------------------------------
  # Arabic subtitle
  # -------------------------------------------------------------------------

  SCENE_TEXT_AR="$(
    jq -r \
      ".scenes[$i].text_ar // .scenes[$i].subtitle_ar // \"\"" \
      "$JOB"
  )"

  # -------------------------------------------------------------------------
  # Pexels query
  # -------------------------------------------------------------------------

  PEXELS_QUERY="$(
    jq -r \
      ".scenes[$i].pexels_query // .scenes[$i].query // .query // \"nature\"" \
      "$JOB"
  )"

  if [ -z "$SCENE_TEXT_EN" ] || [ "$SCENE_TEXT_EN" = "null" ]; then

    echo "WARNING: Scene $((i+1)) has no English text."

    continue

  fi

  if [ -z "$SCENE_TEXT_AR" ] || [ "$SCENE_TEXT_AR" = "null" ]; then

    SCENE_TEXT_AR="$SCENE_TEXT_EN"

  fi

  if [ -z "$PEXELS_QUERY" ] || [ "$PEXELS_QUERY" = "null" ]; then

    PEXELS_QUERY="nature"

  fi

  echo
  echo "================================================"
  echo "SCENE $((i+1)) / $SCENE_COUNT"
  echo "================================================"
  echo "English : $SCENE_TEXT_EN"
  echo "Arabic  : $SCENE_TEXT_AR"
  echo "Visual  : $PEXELS_QUERY"
  echo "================================================"

  TEXT_EN_FILE="$SCENES_DIR/scene_${i}_en.txt"

  AUDIO="$AUDIO_DIR/bella_${i}.wav"

  RAW_VIDEO="$RAW_DIR/raw_${i}.mp4"

  FINAL_SCENE="$VIDEO_DIR/video_${i}.mp4"

  SUB="$SCENES_DIR/sub_${i}.srt"

  printf '%s\n' "$SCENE_TEXT_EN" > "$TEXT_EN_FILE"

  # ========================================================================
  # 9. Generate Bella voice
  # ========================================================================

  echo "Generating Bella voice..."

  (
    cd "$KOKORO_DIR"

    "$KOKORO_BIN" \
      "$TEXT_EN_FILE" \
      "$AUDIO" \
      --voice "af_bella" \
      --speed 1.0 \
      --lang en-us

  )

  if [ ! -s "$AUDIO" ]; then

    echo "ERROR: Kokoro failed for scene $((i+1))."

    exit 1

  fi

  # ========================================================================
  # 10. Audio duration
  # ========================================================================

  SCENE_DUR="$(
    ffprobe \
      -v error \
      -show_entries format=duration \
      -of csv=p=0 \
      "$AUDIO"
  )"

  if [ -z "$SCENE_DUR" ]; then

    echo "ERROR: Could not determine audio duration."

    exit 1

  fi

  echo "Voice duration: ${SCENE_DUR}s"

  # ========================================================================
  # 11. Search Pexels
  # ========================================================================

  VIDEO_URL=""

  if [ -n "$PEXELS_KEY" ]; then

    ENC_QUERY="$(
      printf '%s' "$PEXELS_QUERY" |
      jq -sRr @uri
    )"

    echo "Searching Pexels..."

    mapfile -t LINKS < <(

      curl -fsS \
        --retry 2 \
        --max-time 30 \
        -H "Authorization: $PEXELS_KEY" \
        "https://api.pexels.com/videos/search?query=${ENC_QUERY}&orientation=portrait&size=medium&per_page=20" \
        2>/dev/null |

      jq -r '
        [
          .videos[]?
          | .video_files[]?
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

      PICK_INDEX=$((i % ${#LINKS[@]}))

      VIDEO_URL="${LINKS[$PICK_INDEX]}"

    fi

  fi

  # ========================================================================
  # 12. Download visual
  # ========================================================================

  if [ -n "$VIDEO_URL" ]; then

    echo "Downloading Pexels visual..."

    if ! curl -fL \
      --retry 2 \
      --max-time 120 \
      "$VIDEO_URL" \
      -o "$RAW_VIDEO"; then

      echo "WARNING: Pexels download failed."

      rm -f "$RAW_VIDEO"

    fi

  fi

  # ========================================================================
  # 13. Fallback visual
  # ========================================================================

  if [ ! -s "$RAW_VIDEO" ]; then

    echo "WARNING: No Pexels clip."
    echo "Creating animated fallback..."

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
      "$RAW_VIDEO"

  fi

  # ========================================================================
  # 14. Arabic subtitles
  # ========================================================================

  python3 - \
    "$SCENE_TEXT_AR" \
    "$SUB" \
    "$SCENE_DUR" \
    <<'PY'

import sys
import textwrap

text = sys.argv[1].strip()
out = sys.argv[2]
duration = float(sys.argv[3])

words = text.split()

if not words:

    raise SystemExit(
        "Empty subtitle text"
    )

chunks = [
    " ".join(words[i:i + 5])
    for i in range(0, len(words), 5)
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

    return (
        f"{h:02d}:"
        f"{m:02d}:"
        f"{s:02d},"
        f"{ms:03d}"
    )

with open(
    out,
    "w",
    encoding="utf-8"
) as f:

    for n, chunk in enumerate(
        chunks,
        1
    ):

        start = (
            n - 1
        ) * chunk_duration

        end = min(
            n * chunk_duration,
            duration
        )

        wrapped = "\n".join(
            textwrap.wrap(
                chunk,
                width=24,
                break_long_words=False,
                break_on_hyphens=False
            )
        )

        f.write(
            f"{n}\n"
        )

        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )

        f.write(
            wrapped
        )

        f.write(
            "\n\n"
        )

PY

  # ========================================================================
  # 15. Motion
  # ========================================================================

  case $((i % 4)) in

    0)

      MOTION="zoompan=z='min(zoom+0.0007,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"

      ;;

    1)

      MOTION="zoompan=z='min(zoom+0.0005,1.08)':x='iw/2-(iw/zoom/2)+18*sin(on/20)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"

      ;;

    2)

      MOTION="zoompan=z='min(zoom+0.0006,1.09)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+16*cos(on/18)':d=1:s=1080x1920:fps=30"

      ;;

    3)

      MOTION="zoompan=z='min(zoom+0.0004,1.07)':x='iw/2-(iw/zoom/2)+12*sin(on/16)':y='ih/2-(ih/zoom/2)+12*cos(on/17)':d=1:s=1080x1920:fps=30"

      ;;

  esac

  # ========================================================================
  # 16. Render scene
  # ========================================================================

  echo "Rendering scene..."

  CAPTION_STYLE="FontName=DejaVu Sans,Fontsize=20,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=4,Shadow=2,Alignment=2,MarginV=300"

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -stream_loop -1 \
    -i "$RAW_VIDEO" \
    -i "$AUDIO" \
    -t "$SCENE_DUR" \
    -filter_complex "\
[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,eq=brightness=-0.035:saturation=1.08[base];\
[base]${MOTION}[motion];\
[motion]subtitles='${SUB}':force_style='${CAPTION_STYLE}'[v]" \
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
    "$FINAL_SCENE"

  if [ ! -s "$FINAL_SCENE" ]; then

    echo "ERROR: Scene rendering failed."

    exit 1

  fi

  PARTS+=("$FINAL_SCENE")

  TOTAL_DURATION="$(
    awk \
      -v a="$TOTAL_DURATION" \
      -v b="$SCENE_DUR" \
      'BEGIN {printf "%.3f", a+b}'
  )"

done

# ===========================================================================
# 17. Validate
# ===========================================================================

if [ "${#PARTS[@]}" -lt 1 ]; then

  echo "ERROR: No usable scenes."

  exit 1

fi

echo
echo "================================================"
echo "ALL SCENES READY"
echo "================================================"
echo "Scenes   : ${#PARTS[@]}"
echo "Duration : ${TOTAL_DURATION}s"
echo "Voice    : ${VOICE}"
echo "================================================"

# ===========================================================================
# 18. Concatenate
# ===========================================================================

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

# ===========================================================================
# 19. Validate final
# ===========================================================================

if [ ! -s "$FINAL" ]; then

  echo "ERROR: final video creation failed."

  exit 1

fi

# ===========================================================================
# 20. Copy final
# ===========================================================================

cp "$FINAL" "$OUT"

# ===========================================================================
# 21. Final verification
# ===========================================================================

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
echo "================================================"
echo "FINAL VIDEO READY"
echo "================================================"
echo "Width    : $VIDEO_WIDTH"
echo "Height   : $VIDEO_HEIGHT"
echo "Duration : $FINAL_DURATION"
echo "Scenes   : ${#PARTS[@]}"
echo "Voice    : Kokoro $VOICE"
echo "Speed    : 1.0"
echo "Subtitles: Arabic"
echo "================================================"

echo \
  "{\"video\":\"${OUT}\",\"duration\":${FINAL_DURATION},\"scenes\":${#PARTS[@]},\"voice\":\"${VOICE}\",\"speed\":1.0,\"subtitle\":\"ar\"}"
