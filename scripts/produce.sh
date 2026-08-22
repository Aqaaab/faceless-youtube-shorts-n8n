#!/usr/bin/env bash
# ===========================================================================
# produce.sh
# YouTube Shorts Video Engine
#
# Voice       : Kokoro af_bella
# Language    : English (US)
# Subtitles   : Arabic
# Visuals     : Pexels
# ===========================================================================

set -euo pipefail

RUN_DIR="${1:?Usage: produce.sh <RUN_DIR>}"
JOB="$RUN_DIR/job.json"

if [ ! -s "$JOB" ]; then
  echo "ERROR: $JOB missing"
  exit 1
fi

# ===========================================================================
# Configuration
# ===========================================================================

PEXELS_KEY="${PEXELS_API_KEY:-}"
GROQ_KEY="${GROQ_API_KEY:-}"

VOICE="af_bella"
SPEED="1.0"
LANG="en-us"

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

echo
echo "================================================"
echo "      KOKORO BELLA SHORTS ENGINE"
echo "================================================"
echo "Voice       : $VOICE"
echo "Speed       : $SPEED"
echo "Language    : $LANG"
echo "Subtitles   : Arabic"
echo "Pexels      : $([ -n "$PEXELS_KEY" ] && echo ENABLED || echo DISABLED)"
echo "================================================"
echo

# ===========================================================================
# Check basic dependencies
# ===========================================================================

echo "Checking dependencies..."

for CMD in python3 jq ffmpeg ffprobe curl awk; do
  if ! command -v "$CMD" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $CMD"
    exit 1
  fi
done

echo "Basic dependencies OK."

# ===========================================================================
# PortAudio
#
# Kokoro's CLI imports sounddevice. sounddevice requires libportaudio.
# Install only when necessary.
# ===========================================================================

echo "Checking PortAudio..."

PORTAUDIO_OK="false"

python3 - <<'PY' >/dev/null 2>&1
try:
    import ctypes.util
    lib = ctypes.util.find_library("portaudio")
    raise SystemExit(0 if lib else 1)
except Exception:
    raise SystemExit(1)
PY

if [ "$?" -eq 0 ]; then
  PORTAUDIO_OK="true"
fi

if [ "$PORTAUDIO_OK" != "true" ]; then

  echo "PortAudio not found."

  if command -v apt-get >/dev/null 2>&1; then

    echo "Installing PortAudio packages..."

    if command -v sudo >/dev/null 2>&1; then

      sudo apt-get update -qq

      sudo apt-get install -y -qq \
        libportaudio2 \
        portaudio19-dev \
        libsndfile1

    else

      apt-get update -qq

      apt-get install -y -qq \
        libportaudio2 \
        portaudio19-dev \
        libsndfile1

    fi

  fi

fi

# Verify again.
python3 - <<'PY'
import ctypes.util

lib = ctypes.util.find_library("portaudio")

if not lib:
    raise SystemExit(
        "ERROR: PortAudio library is still unavailable. "
        "Kokoro/sounddevice cannot start."
    )

print("PortAudio:", lib)
PY

echo "PortAudio OK."

# ===========================================================================
# Install Kokoro
# ===========================================================================

echo "Checking Kokoro Python package..."

if ! python3 -c "import kokoro_tts" >/dev/null 2>&1; then

  echo "Installing kokoro..."

  python3 -m pip install \
    --user \
    --quiet \
    --upgrade \
    kokoro-tts

fi

KOKORO_BIN="$(command -v kokoro-tts || true)"

if [ -z "$KOKORO_BIN" ]; then

  USER_BIN="$(python3 -m site --user-base)/bin/kokoro-tts"

  if [ -x "$USER_BIN" ]; then
    KOKORO_BIN="$USER_BIN"
  fi

fi

if [ -z "$KOKORO_BIN" ] || [ ! -x "$KOKORO_BIN" ]; then
  echo "ERROR: kokoro-tts executable not found."
  exit 1
fi

echo "Kokoro: $KOKORO_BIN"

# ===========================================================================
# Download Kokoro model
# ===========================================================================

KOKORO_MODEL="$KOKORO_DIR/kokoro-v1.0.onnx"
KOKORO_VOICES="$KOKORO_DIR/voices-v1.0.bin"

KOKORO_MODEL_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"

if [ ! -s "$KOKORO_MODEL" ]; then

  echo "Downloading Kokoro model..."

  curl -fL \
    --retry 5 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 900 \
    "$KOKORO_MODEL_URL" \
    -o "$KOKORO_MODEL"

fi

if [ ! -s "$KOKORO_VOICES" ]; then

  echo "Downloading Kokoro voices..."

  curl -fL \
    --retry 5 \
    --retry-delay 2 \
    --connect-timeout 20 \
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
# Validate job
# ===========================================================================

echo
echo "Preparing job..."

SCENE_COUNT="$(
  jq -r '
    if (.scenes | type) == "array"
    then (.scenes | length)
    else 0
    end
  ' "$JOB"
)"

if [ "$SCENE_COUNT" -lt 1 ]; then

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

sentences = re.split(r'(?<=[.!?])\s+', script)

sentences = [
    x.strip()
    for x in sentences
    if x.strip()
]

target = 5

if len(sentences) <= target:
    groups = sentences
else:
    per_group = max(
        1,
        (len(sentences) + target - 1) // target
    )

    groups = []

    for i in range(0, len(sentences), per_group):
        groups.append(
            " ".join(sentences[i:i + per_group])
        )

job = json.load(open(job_file, encoding="utf-8"))

job["voice"] = "af_bella"

job["scenes"] = [
    {
        "text_en": text,
        "text_ar": text,
        "pexels_query": query
    }
    for text in groups
]

with open(
    job_file,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        job,
        f,
        ensure_ascii=False,
        indent=2
    )

print("Created", len(job["scenes"]), "scenes.")

PY

  SCENE_COUNT="$(
    jq -r '.scenes | length' "$JOB"
  )"

fi

if [ "$SCENE_COUNT" -lt 1 ]; then
  echo "ERROR: No usable scenes."
  exit 1
fi

echo "Scenes: $SCENE_COUNT"

# ===========================================================================
# Detect Arabic
# ===========================================================================

contains_arabic() {
  python3 - "$1" <<'PY'
import sys

text = sys.argv[1]

arabic = sum(
    1
    for c in text
    if '\u0600' <= c <= '\u06ff'
)

letters = sum(
    1
    for c in text
    if c.isalpha()
)

if letters > 0 and arabic / letters > 0.20:
    raise SystemExit(0)

raise SystemExit(1)
PY
}

# ===========================================================================
# Repair English narration if Groq accidentally returned Arabic
# ===========================================================================

repair_english_with_groq() {

  local TEXT="$1"

  if [ -z "$GROQ_KEY" ]; then
    echo "ERROR: GROQ_API_KEY is missing."
    echo "Cannot repair Arabic text_en."
    exit 1
  fi

  echo "Groq returned non-English narration."
  echo "Repairing text_en..."

  local PAYLOAD
  local RESPONSE
  local RESULT

  PAYLOAD="$(
    jq -n \
      --arg text "$TEXT" \
      '{
        model: "llama-3.3-70b-versatile",
        temperature: 0.2,
        response_format: {
          type: "json_object"
        },
        messages: [
          {
            role: "system",
            content:
              "Translate the supplied narration into natural conversational English for a YouTube Short. Return ONLY JSON with exactly one key: text_en. Preserve the factual meaning. Do not add facts. Do not use markdown."
          },
          {
            role: "user",
            content: $text
          }
        ]
      }'
  )"

  RESPONSE="$(
    curl -fsS \
      --retry 3 \
      --connect-timeout 20 \
      --max-time 90 \
      -H "Authorization: Bearer ${GROQ_KEY}" \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD" \
      "https://api.groq.com/openai/v1/chat/completions"
  )"

  RESULT="$(
    printf '%s' "$RESPONSE" |
    jq -r '.choices[0].message.content // empty'
  )"

  if [ -z "$RESULT" ]; then
    echo "ERROR: Groq translation returned no content."
    exit 1
  fi

  printf '%s' "$RESULT" |
    jq -r '.text_en // empty' 2>/dev/null || true
}

# ===========================================================================
# Split long narration into safe TTS chunks
# ===========================================================================

generate_tts() {

  local TEXT_FILE="$1"
  local OUTPUT_WAV="$2"

  local TMP_DIR
  TMP_DIR="$(
    mktemp -d "$RUN_DIR/tts.XXXXXX"
  )"

  trap 'rm -rf "$TMP_DIR"' RETURN

  python3 \
    "$TEXT_FILE" \
    "$TMP_DIR/chunks" \
    <<'PY'
import sys
import os
import re

src = sys.argv[1]
out_dir = sys.argv[2]

os.makedirs(out_dir, exist_ok=True)

text = open(
    src,
    encoding="utf-8"
).read().strip()

# Split by sentence first.
sentences = re.split(
    r'(?<=[.!?])\s+',
    text
)

sentences = [
    s.strip()
    for s in sentences
    if s.strip()
]

chunks = []
current = []

# Keep each TTS chunk comfortably below Kokoro's phoneme limit.
MAX_WORDS = 45

for sentence in sentences:

    words = sentence.split()

    if len(words) <= MAX_WORDS:

        if len(current) + len(words) > MAX_WORDS:
            chunks.append(" ".join(current))
            current = []

        current.extend(words)

    else:

        if current:
            chunks.append(" ".join(current))
            current = []

        for i in range(0, len(words), MAX_WORDS):
            chunks.append(
                " ".join(words[i:i + MAX_WORDS])
            )

if current:
    chunks.append(" ".join(current))

if not chunks:
    chunks = [text]

for i, chunk in enumerate(chunks):

    with open(
        os.path.join(
            out_dir,
            f"{i:04d}.txt"
        ),
        "w",
        encoding="utf-8"
    ) as f:
        f.write(chunk)

print(len(chunks))

PY

  mapfile -t CHUNKS < <(
    find "$TMP_DIR/chunks" \
      -type f \
      -name '*.txt' |
    sort
  )

  if [ "${#CHUNKS[@]}" -eq 0 ]; then
    echo "ERROR: No TTS chunks created."
    return 1
  fi

  local WAV_PARTS=()

  for ((c=0; c<${#CHUNKS[@]}; c++)); do

    local PART="$TMP_DIR/part_${c}.wav"

    echo "TTS chunk $((c+1))/${#CHUNKS[@]}"

    "$KOKORO_BIN" \
      "${CHUNKS[$c]}" \
      "$PART" \
      --voice "$VOICE" \
      --speed "$SPEED" \
      --lang "$LANG"

    if [ ! -s "$PART" ]; then
      echo "ERROR: Kokoro failed on chunk $((c+1))."
      return 1
    fi

    WAV_PARTS+=("$PART")

  done

  if [ "${#WAV_PARTS[@]}" -eq 1 ]; then

    cp \
      "${WAV_PARTS[0]}" \
      "$OUTPUT_WAV"

  else

    local CONCAT="$TMP_DIR/audio.txt"

    : > "$CONCAT"

    for W in "${WAV_PARTS[@]}"; do
      printf "file '%s'\n" "$W" >> "$CONCAT"
    done

    ffmpeg -y \
      -hide_banner \
      -loglevel error \
      -f concat \
      -safe 0 \
      -i "$CONCAT" \
      -c:a pcm_s16le \
      "$OUTPUT_WAV"

  fi

  [ -s "$OUTPUT_WAV" ]

}

# ===========================================================================
# Generate scenes
# ===========================================================================

PARTS=()
TOTAL_DURATION="0"

for ((i=0; i<SCENE_COUNT; i++)); do

  SCENE_TEXT_EN="$(
    jq -r \
      ".scenes[$i].text_en // .scenes[$i].text // \"\"" \
      "$JOB"
  )"

  SCENE_TEXT_AR="$(
    jq -r \
      ".scenes[$i].text_ar // .scenes[$i].subtitle_ar // \"\"" \
      "$JOB"
  )"

  PEXELS_QUERY="$(
    jq -r \
      ".scenes[$i].pexels_query // .scenes[$i].query // .query // \"nature\"" \
      "$JOB"
  )"

  if [ -z "$SCENE_TEXT_EN" ] || [ "$SCENE_TEXT_EN" = "null" ]; then
    echo "ERROR: Scene $((i+1)) has no English text."
    exit 1
  fi

  if [ -z "$SCENE_TEXT_AR" ] || [ "$SCENE_TEXT_AR" = "null" ]; then
    SCENE_TEXT_AR="$SCENE_TEXT_EN"
  fi

  if [ -z "$PEXELS_QUERY" ] || [ "$PEXELS_QUERY" = "null" ]; then
    PEXELS_QUERY="nature"
  fi

  # -------------------------------------------------------------------------
  # Detect accidental Arabic in text_en.
  # -------------------------------------------------------------------------

  if contains_arabic "$SCENE_TEXT_EN"; then

    echo "WARNING: Scene $((i+1)) text_en contains Arabic."

    FIXED_EN="$(
      repair_english_with_groq "$SCENE_TEXT_EN"
    )"

    if [ -z "$FIXED_EN" ]; then
      echo "ERROR: Could not repair English narration."
      exit 1
    fi

    SCENE_TEXT_EN="$FIXED_EN"

    echo "English narration repaired."

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

  # =========================================================================
  # TTS
  # =========================================================================

  echo "Generating Bella voice..."

  generate_tts \
    "$TEXT_EN_FILE" \
    "$AUDIO"

  if [ ! -s "$AUDIO" ]; then
    echo "ERROR: Kokoro failed for scene $((i+1))."
    exit 1
  fi

  # =========================================================================
  # Audio duration
  # =========================================================================

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

  # =========================================================================
  # Pexels
  # =========================================================================

  VIDEO_URL=""

  if [ -n "$PEXELS_KEY" ]; then

    ENC_QUERY="$(
      printf '%s' "$PEXELS_QUERY" |
      jq -sRr @uri
    )"

    echo "Searching Pexels..."

    mapfile -t LINKS < <(

      curl -fsS \
        --retry 3 \
        --connect-timeout 15 \
        --max-time 45 \
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

  # =========================================================================
  # Download visual
  # =========================================================================

  if [ -n "$VIDEO_URL" ]; then

    echo "Downloading Pexels visual..."

    if ! curl -fL \
      --retry 3 \
      --connect-timeout 15 \
      --max-time 180 \
      "$VIDEO_URL" \
      -o "$RAW_VIDEO"; then

      echo "WARNING: Pexels download failed."
      rm -f "$RAW_VIDEO"

    fi

  fi

  # =========================================================================
  # Fallback visual
  # =========================================================================

  if [ ! -s "$RAW_VIDEO" ]; then

    echo "WARNING: No Pexels clip."
    echo "Creating fallback visual..."

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

  # =========================================================================
  # Arabic subtitles
  # =========================================================================

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
    raise SystemExit("Empty subtitle text")

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

    for n, chunk in enumerate(chunks, 1):

        start = (n - 1) * chunk_duration
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

        f.write(f"{n}\n")
        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )
        f.write(wrapped)
        f.write("\n\n")

PY

  # =========================================================================
  # Motion
  # =========================================================================

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

  # =========================================================================
  # Render
  # =========================================================================

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
    "$FINAL_SCENE
