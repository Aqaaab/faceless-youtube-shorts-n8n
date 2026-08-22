#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="${1:?Usage: produce.sh <RUN_DIR>}"
JOB="$RUN_DIR/job.json"

[ -s "$JOB" ] || {
  echo "ERROR: $JOB missing" >&2
  exit 1
}

PEXELS_KEY="${PEXELS_API_KEY:-}"
VOICE="$(jq -r '.voice // "ar_JO-kareem-medium"' "$JOB")"

OUT="$RUN_DIR/video.mp4"

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
echo "ANIME STYLE ARABIC SHORTS ENGINE"
echo "Scenes: $SCENE_COUNT"
echo "Voice: $VOICE"
echo "=============================================="

# ============================================================
# 1. Install Piper
# ============================================================

python3 -m pip install \
  --quiet \
  --upgrade \
  piper-tts

# ============================================================
# 2. Arabic Piper model
# ============================================================

MODEL="$PIPER_DIR/ar_JO-kareem-medium.onnx"
MODEL_JSON="$PIPER_DIR/ar_JO-kareem-medium.onnx.json"

MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx?download=true"

MODEL_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json?download=true"

if [ ! -s "$MODEL" ]; then
  echo "Downloading Arabic voice model..."

  curl -fL \
    --retry 3 \
    --retry-delay 2 \
    --max-time 300 \
    "$MODEL_URL" \
    -o "$MODEL"
fi

if [ ! -s "$MODEL_JSON" ]; then
  echo "Downloading voice configuration..."

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
  echo "ERROR: Piper configuration missing." >&2
  exit 1
}

echo "Piper ready."

# ============================================================
# 3. Generate every scene
# ============================================================

PARTS=()
TOTAL_DURATION=0

for ((i=0; i<SCENE_COUNT; i++)); do

  SCENE_TEXT="$(
    jq -r ".scenes[$i].text // \"\"" "$JOB"
  )"

  PEXELS_QUERY="$(
    jq -r ".scenes[$i].pexels_query // \"nature\"" "$JOB"
  )"

  if [ -z "$SCENE_TEXT" ]; then
    echo "WARNING: Empty scene $((i+1))."
    continue
  fi

  [ -n "$PEXELS_QUERY" ] || PEXELS_QUERY="nature"

  echo
  echo "=============================================="
  echo "SCENE $((i+1)) / $SCENE_COUNT"
  echo "VISUAL: $PEXELS_QUERY"
  echo "=============================================="

  TEXT_FILE="$SCENES_DIR/scene_${i}.txt"

  RAW_AUDIO="$AUDIO_DIR/raw_${i}.wav"
  ANIME_AUDIO="$AUDIO_DIR/anime_${i}.wav"

  RAW_VIDEO="$RAW_DIR/raw_${i}.mp4"
  FINAL_SCENE="$VIDEO_DIR/video_${i}.mp4"

  SUB="$SCENES_DIR/sub_${i}.srt"

  printf '%s\n' "$SCENE_TEXT" > "$TEXT_FILE"

  # ==========================================================
  # 4. Generate Arabic voice
  # ==========================================================

  echo "Generating Arabic voice..."

  python3 -m piper \
    --model "$MODEL" \
    --output_file "$RAW_AUDIO" \
    --sentence-silence 0.08 \
    < "$TEXT_FILE"

  [ -s "$RAW_AUDIO" ] || {
    echo "ERROR: Piper failed." >&2
    exit 1
  }

  # ==========================================================
  # 5. Anime-style voice processing
  #
  # Higher pitch + slight speed increase + compression.
  #
  # We alternate the pitch slightly between scenes so the
  # entire Short does not sound mechanically identical.
  # ==========================================================

  case $((i % 3)) in
    0)
      PITCH=1.16
      SPEED=1.05
      ;;
    1)
      PITCH=1.20
      SPEED=1.07
      ;;
    2)
      PITCH=1.13
      SPEED=1.04
      ;;
  esac

  echo "Applying anime voice profile..."
  echo "Pitch: $PITCH"
  echo "Speed: $SPEED"

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -i "$RAW_AUDIO" \
    -filter_complex \
    "[0:a]asetrate=44100*${PITCH},aresample=44100,atempo=${SPEED},acompressor=threshold=-18dB:ratio=3:attack=5:release=80,volume=1.15,alimiter=limit=0.92[voice]" \
    -map "[voice]" \
    -ar 44100 \
    -ac 2 \
    "$ANIME_AUDIO"

  [ -s "$ANIME_AUDIO" ] || {
    echo "ERROR: Anime voice processing failed." >&2
    exit 1
  }

  SCENE_DUR="$(
    ffprobe \
      -v error \
      -show_entries format=duration \
      -of csv=p=0 \
      "$ANIME_AUDIO"
  )"

  echo "Anime voice duration: ${SCENE_DUR}s"

  # ==========================================================
  # 6. Search Pexels for this exact scene
  # ==========================================================

  VIDEO_URL=""

  if [ -n "$PEXELS_KEY" ]; then

    ENC_QUERY="$(
      printf '%s' "$PEXELS_QUERY" |
      jq -sRr @uri
    )"

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

      PICK_INDEX=$((i % ${#LINKS[@]}))

      VIDEO_URL="${LINKS[$PICK_INDEX]}"

    fi

  fi

  # ==========================================================
  # 7. Download scene video
  # ==========================================================

  if [ -n "$VIDEO_URL" ]; then

    echo "Downloading matching scene..."

    if ! curl -fL \
      --retry 2 \
      --max-time 120 \
      "$VIDEO_URL" \
      -o "$RAW_VIDEO"; then

      echo "WARNING: Pexels download failed."
      VIDEO_URL=""

    fi

  fi

  # ==========================================================
  # 8. Animated fallback
  # ==========================================================

  if [ ! -s "$RAW_VIDEO" ]; then

    echo "Creating animated fallback."

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

  # ==========================================================
  # 9. Generate subtitles
  # ==========================================================

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
    raise SystemExit("Empty scene")

chunks = [
    " ".join(words[i:i+5])
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

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

with open(out, "w", encoding="utf-8") as f:

    for n, chunk in enumerate(chunks, 1):

        start = (n - 1) * chunk_duration
        end = min(n * chunk_duration, duration)

        wrapped = "\n".join(
            textwrap.wrap(
                chunk,
                width=24,
                break_long_words=False,
                break_on_hyphens=False
            )
        )

        f.write(f"{n}\n")
        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )
        f.write(wrapped)
        f.write("\n\n")

PY

  # ==========================================================
  # 10. Render scene
  #
  # Each scene has:
  # - its own video
  # - its own voice
  # - its own duration
  # - zoom movement
  # - slight rotation
  # - captions
  # ==========================================================

  echo "Rendering animated scene..."

  CAPTION_STYLE="FontName=DejaVu Sans,Fontsize=20,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=4,Shadow=2,Alignment=2,MarginV=300"

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

  ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -stream_loop -1 \
    -i "$RAW_VIDEO" \
    -i "$ANIME_AUDIO" \
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

  [ -s "$FINAL_SCENE" ] || {
    echo "ERROR: Scene rendering failed." >&2
    exit 1
  }

  PARTS+=("$FINAL_SCENE")

  TOTAL_DURATION="$(
    awk \
      -v a="$TOTAL_DURATION" \
      -v b="$SCENE_DUR" \
      'BEGIN {printf "%.3f", a+b}'
  )"

done

# ============================================================
# 11. Validate
# ============================================================

if [ "${#PARTS[@]}" -lt 4 ]; then
  echo "ERROR: fewer than 4 usable scenes." >&2
  exit 1
fi

echo
echo "=============================================="
echo "ALL SCENES READY"
echo "Scenes: ${#PARTS[@]}"
echo "Duration: ${TOTAL_DURATION}s"
echo "=============================================="

# ============================================================
# 12. Concatenate scenes
# ============================================================

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

# ============================================================
# 13. Final verification
# ============================================================

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
echo "ANIME STYLE SHORT READY"
echo "=============================================="
echo "Width:    $VIDEO_WIDTH"
echo "Height:   $VIDEO_HEIGHT"
echo "Duration: $FINAL_DURATION"
echo "Scenes:   ${#PARTS[@]}"
echo "Voice:    Anime-style Arabic"
echo "=============================================="

echo \
  "{\"video\":\"${OUT}\",\"duration\":${FINAL_DURATION},\"scenes\":${#PARTS[@]},\"voice\":\"anime-style-arabic\"}"
