#!/usr/bin/env bash
# ===========================================================================
# produce.sh — Arabic YouTube Shorts scene-based media engine
#
# TTS:
#   Microsoft Edge TTS — Arabic Neural
#   No API key required
#
# Voice style:
#   ar-SA-HamedNeural
#   Faster + slightly higher pitch for an energetic anime-narrator feel.
#
# Input:
#   <RUN_DIR>/job.json
#
# Expected:
# {
#   "script": "...",
#   "voice": "ar-SA-HamedNeural",
#   "scenes": [
#     {
#       "text": "...",
#       "pexels_query": "octopus ocean"
#     }
#   ]
# }
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

# Always use the selected Arabic Neural voice.
# The workflow may still contain the old Piper voice, so we deliberately
# override it here.
VOICE="ar-SA-HamedNeural"

OUT="$RUN_DIR/video.mp4"

SCENES_DIR="$RUN_DIR/scenes"
AUDIO_DIR="$SCENES_DIR/audio"
VIDEO_DIR="$SCENES_DIR/video"
RAW_DIR="$SCENES_DIR/raw"

mkdir -p \
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
echo "Arabic Anime-Style Shorts Engine"
echo "Scenes: $SCENE_COUNT"
echo "Voice: $VOICE"
echo "=============================================="

# ---------------------------------------------------------------------------
# Install Edge TTS
# ---------------------------------------------------------------------------

echo "Installing/checking Edge TTS..."

python3 -m pip install \
  --quiet \
  --upgrade \
  edge-tts

# ---------------------------------------------------------------------------
# Generate every scene independently
# ---------------------------------------------------------------------------

PARTS=()
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
  AUDIO="$AUDIO_DIR/audio_${i}.mp3"
  RAW="$RAW_DIR/raw_${i}.mp4"
  VIDEO="$VIDEO_DIR/video_${i}.mp4"

  printf '%s\n' "$SCENE_TEXT" > "$SCENE_TEXT_FILE"

  # -------------------------------------------------------------------------
  # Generate energetic Arabic Neural voice
  #
  # +10% speed keeps Shorts punchy.
  # +8Hz pitch gives a slightly brighter animated character.
  # -------------------------------------------------------------------------

  echo "Generating Arabic Neural voice..."

  edge-tts \
    --voice "$VOICE" \
    --rate="+10%" \
    --pitch="+8Hz" \
    --volume="+0%" \
    --text "$SCENE_TEXT" \
    --write-media "$AUDIO"

  [ -s "$AUDIO" ] || {
    echo "ERROR: Edge TTS failed for scene $i." >&2
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
  # Search Pexels for THIS scene
  # -------------------------------------------------------------------------

  VIDEO_URL=""

  if [ -n "$PEXELS_KEY" ]; then

    ENC_QUERY="$(
      printf '%s' "$PEXELS_QUERY" |
      jq -sRr @uri
    )"

    echo "Searching Pexels: $PEXELS_QUERY"

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

      # Vary selected result between scenes.
      PICK_INDEX=$((i % ${#LINKS[@]}))

      VIDEO_URL="${LINKS[$PICK_INDEX]}"

    fi

  fi

  # -------------------------------------------------------------------------
  # Download matching scene
  # -------------------------------------------------------------------------

  if [ -n "$VIDEO_URL" ]; then

    echo "Downloading matching visual..."

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
  # Animated fallback
  # -------------------------------------------------------------------------

  if [ ! -s "$RAW" ]; then

    echo "WARNING: No Pexels clip."
    echo "Creating animated fallback."

    DUR_INT="$(
      awk "BEGIN {print int($SCENE_DUR + 0.999)}"
    )"

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
      "$RAW"

  fi

  # -------------------------------------------------------------------------
  # Render scene
  #
  # Each scene follows its OWN voice duration.
  # No single clip is allowed to cover the entire narration.
  # -------------------------------------------------------------------------

  echo "Rendering scene..."

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -stream_loop -1 \
    -i "$RAW" \
    -i "$AUDIO" \
    -t "$SCENE_DUR" \
    -filter_complex "\
[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920:x='(in_w-out_w)/2+12*sin(t*0.35)':y='(in_h-out_h)/2+10*cos(t*0.30)',setsar=1,fps=30,eq=brightness=-0.04:saturation=1.08,unsharp=5:5:0.5:5:5:0[v0];\
[v0]drawbox=x=0:y=0:w=iw:h=iw*0.12:color=black@0.12:t=fill[v]" \
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

  TOTAL_DURATION="$(
    awk \
      -v a="$TOTAL_DURATION" \
      -v b="$SCENE_DUR" \
      'BEGIN {printf "%.3f", a+b}'
  )"

done

# ---------------------------------------------------------------------------
# Verify scenes
# ---------------------------------------------------------------------------

if [ "${#PARTS[@]}" -lt 4 ]; then
  echo "ERROR: fewer than 4 usable scenes." >&2
  exit 1
fi

echo
echo "=============================================="
echo "All scenes rendered"
echo "Usable scenes: ${#PARTS[@]}"
echo "Total duration: ${TOTAL_DURATION}s"
echo "=============================================="

# ---------------------------------------------------------------------------
# Concatenate scenes
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

cp "$FINAL" "$OUT"

# ---------------------------------------------------------------------------
# Verify final video
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
echo "Style:    Energetic Arabic Anime"
echo "=============================================="

echo \
  "{\"video\":\"${OUT}\",\"duration\":${FINAL_DURATION},\"scenes\":${#PARTS[@]},\"voice\":\"${VOICE}\",\"style\":\"anime-energetic\"}"
