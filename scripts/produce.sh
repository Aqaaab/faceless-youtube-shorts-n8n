#!/usr/bin/env bash

# ===========================================================================
# produce.sh
# YouTube Shorts Video Engine
# Voice    : Kokoro af_bella
# Language : English (US)
# Subtitles: Arabic
# ===========================================================================

set -euo pipefail

# ===========================================================================
# INPUT
# ===========================================================================

RUN_DIR="${1:?Usage: produce.sh <RUN_DIR>}"
JOB="$RUN_DIR/job.json"

if [ ! -f "$JOB" ] || [ ! -s "$JOB" ]; then
    echo "ERROR: job.json not found: $JOB"
    exit 1
fi

# ===========================================================================
# CONFIGURATION
# ===========================================================================

VOICE="af_bella"
SPEED="1.0"
LANG="en-us"

PEXELS_KEY="${PEXELS_API_KEY:-}"

OUT="$RUN_DIR/video.mp4"

KOKORO_DIR="$RUN_DIR/kokoro"
SCENES_DIR="$RUN_DIR/scenes"
AUDIO_DIR="$SCENES_DIR/audio"
AUDIO_CHUNKS_DIR="$AUDIO_DIR/chunks"
VIDEO_DIR="$SCENES_DIR/video"
RAW_DIR="$SCENES_DIR/raw"

mkdir -p \
    "$KOKORO_DIR" \
    "$SCENES_DIR" \
    "$AUDIO_DIR" \
    "$AUDIO_CHUNKS_DIR" \
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
# CHECK DEPENDENCIES
# ===========================================================================

echo "Checking dependencies..."

for cmd in \
    python3 \
    pip3 \
    ffmpeg \
    ffprobe \
    jq \
    curl \
    awk \
    sed
do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $cmd"
        exit 1
    fi
done

echo "System dependencies OK."

# ===========================================================================
# INSTALL PYTHON PACKAGES
# ===========================================================================

echo "Checking Kokoro Python package..."

if ! python3 -c "import kokoro" >/dev/null 2>&1; then

    echo "Installing kokoro..."

    python3 -m pip install \
        --user \
        --quiet \
        kokoro-tts

fi

# sounddevice is NOT required for file generation.
# This avoids the PortAudio problem on GitHub Actions.

# ===========================================================================
# LOCATE KOKORO
# ===========================================================================

KOKORO_BIN="$(command -v kokoro-tts || true)"

if [ -z "$KOKORO_BIN" ]; then

    USER_BIN="$(python3 -m site --user-base 2>/dev/null)/bin/kokoro-tts"

    if [ -x "$USER_BIN" ]; then
        KOKORO_BIN="$USER_BIN"
    fi

fi

if [ -z "$KOKORO_BIN" ] || [ ! -x "$KOKORO_BIN" ]; then
    echo "ERROR: kokoro-tts executable not found."
    echo "PATH=$PATH"
    exit 1
fi

echo "Kokoro: $KOKORO_BIN"

# ===========================================================================
# KOKORO MODEL
# ===========================================================================

KOKORO_MODEL="$KOKORO_DIR/kokoro-v1.0.onnx"
KOKORO_VOICES="$KOKORO_DIR/voices-v1.0.bin"

KOKORO_MODEL_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"

if [ ! -s "$KOKORO_MODEL" ]; then

    echo "Downloading Kokoro model..."

    curl -fL \
        --retry 5 \
        --retry-delay 3 \
        --connect-timeout 20 \
        --max-time 900 \
        "$KOKORO_MODEL_URL" \
        -o "$KOKORO_MODEL"

fi

if [ ! -s "$KOKORO_VOICES" ]; then

    echo "Downloading Kokoro voices..."

    curl -fL \
        --retry 5 \
        --retry-delay 3 \
        --connect-timeout 20 \
        --max-time 900 \
        "$KOKORO_VOICES_URL" \
        -o "$KOKORO_VOICES"

fi

if [ ! -s "$KOKORO_MODEL" ]; then
    echo "ERROR: Kokoro model is missing."
    exit 1
fi

if [ ! -s "$KOKORO_VOICES" ]; then
    echo "ERROR: Kokoro voices are missing."
    exit 1
fi

echo "Kokoro model ready."

# ===========================================================================
# READ JOB
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

# ===========================================================================
# FALLBACK: BUILD SCENES FROM SCRIPT
# ===========================================================================

if [ "$SCENE_COUNT" -eq 0 ]; then

    SCRIPT_TEXT="$(
        jq -r '.script // .text // ""' "$JOB"
    )"

    QUERY="$(
        jq -r '.query // "nature"' "$JOB"
    )"

    if [ -z "$SCRIPT_TEXT" ] || [ "$SCRIPT_TEXT" = "null" ]; then
        echo "ERROR: job.json contains no scenes and no script."
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
    s.strip()
    for s in sentences
    if s.strip()
]

target = 6

groups = []

if len(sentences) <= target:
    groups = sentences
else:
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

with open(job_file, "w", encoding="utf-8") as f:
    json.dump(
        job,
        f,
        ensure_ascii=False,
        indent=2
    )

print("Created", len(scenes), "scenes.")

PY

    SCENE_COUNT="$(
        jq -r '.scenes | length' "$JOB"
    )"

fi

if [ "$SCENE_COUNT" -lt 1 ]; then
    echo "ERROR: No scenes available."
    exit 1
fi

echo "Scenes: $SCENE_COUNT"

# ===========================================================================
# FUNCTION: GENERATE KOKORO AUDIO
#
# IMPORTANT:
# Kokoro has a phoneme limit per processing chunk.
# We therefore split long narration before TTS.
# ===========================================================================

generate_audio() {

    local TEXT="$1"
    local OUTPUT="$2"
    local PREFIX="$3"

    local TEXT_FILE="$AUDIO_CHUNKS_DIR/${PREFIX}_full.txt"

    printf '%s\n' "$TEXT" > "$TEXT_FILE"

    # Remove previous chunks.
    rm -f "$AUDIO_CHUNKS_DIR/${PREFIX}"_chunk_*.txt
    rm -f "$AUDIO_CHUNKS_DIR/${PREFIX}"_chunk_*.wav

    # -----------------------------------------------------------------------
    # Split by sentence first.
    # Keep chunks deliberately small to avoid Kokoro phoneme truncation.
    # -----------------------------------------------------------------------

    python3 - "$TEXT_FILE" "$AUDIO_CHUNKS_DIR" "$PREFIX" <<'PY'

import sys
import re
from pathlib import Path

text_file = sys.argv[1]
out_dir = Path(sys.argv[2])
prefix = sys.argv[3]

text = Path(text_file).read_text(
    encoding="utf-8"
).strip()

if not text:
    raise SystemExit("Empty TTS text")

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
current_words = 0

# Keep chunks around 18-28 words.
# This is intentionally conservative for Kokoro.
MAX_WORDS = 24

for sentence in sentences:

    words = sentence.split()

    if not words:
        continue

    if current and current_words + len(words) > MAX_WORDS:

        chunks.append(" ".join(current))

        current = []
        current_words = 0

    # A single unusually long sentence.
    if len(words) > MAX_WORDS:

        for i in range(0, len(words), MAX_WORDS):

            part = words[i:i + MAX_WORDS]

            if current:
                chunks.append(" ".join(current))
                current = []
                current_words = 0

            chunks.append(" ".join(part))

        continue

    current.extend(words)
    current_words += len(words)

if current:
    chunks.append(" ".join(current))

if not chunks:
    chunks = [text]

for i, chunk in enumerate(chunks, 1):

    path = out_dir / f"{prefix}_chunk_{i:03d}.txt"

    path.write_text(
        chunk,
        encoding="utf-8"
    )

print(len(chunks))

PY

    CHUNK_COUNT="$(
        find "$AUDIO_CHUNKS_DIR" \
            -maxdepth 1 \
            -type f \
            -name "${PREFIX}_chunk_*.txt" |
        sort |
        wc -l
    )"

    if [ "$CHUNK_COUNT" -lt 1 ]; then
        echo "ERROR: Failed to split TTS text."
        return 1
    fi

    echo "TTS chunks: $CHUNK_COUNT"

    local CHUNK_INDEX=0
    local CHUNK

    for CHUNK in $(
        find "$AUDIO_CHUNKS_DIR" \
            -maxdepth 1 \
            -type f \
            -name "${PREFIX}_chunk_*.txt" |
        sort
    ); do

        CHUNK_INDEX=$((CHUNK_INDEX + 1))

        local WAV="$AUDIO_CHUNKS_DIR/${PREFIX}_chunk_$(printf '%03d' "$CHUNK_INDEX").wav"

        echo "Kokoro chunk $CHUNK_INDEX/$CHUNK_COUNT"

        "$KOKORO_BIN" \
            "$CHUNK" \
            "$WAV" \
            --voice "$VOICE" \
            --speed "$SPEED" \
            --lang "$LANG"

        if [ ! -s "$WAV" ]; then
            echo "ERROR: Kokoro produced no audio."
            return 1
        fi

    done

    # -----------------------------------------------------------------------
    # Join audio chunks.
    # -----------------------------------------------------------------------

    local CONCAT_LIST="$AUDIO_CHUNKS_DIR/${PREFIX}_concat.txt"

    : > "$CONCAT_LIST"

    for CHUNK in $(
        find "$AUDIO_CHUNKS_DIR" \
            -maxdepth 1 \
            -type f \
            -name "${PREFIX}_chunk_*.wav" |
        sort
    ); do

        printf "file '%s'\n" "$CHUNK" >> "$CONCAT_LIST"

    done

    if [ "$CHUNK_COUNT" -eq 1 ]; then

        cp \
            "$AUDIO_CHUNKS_DIR/${PREFIX}_chunk_001.wav" \
            "$OUTPUT"

    else

        ffmpeg -y \
            -hide_banner \
            -loglevel error \
            -f concat \
            -safe 0 \
            -i "$CONCAT_LIST" \
            -c:a pcm_s16le \
            "$OUTPUT"

    fi

    if [ ! -s "$OUTPUT" ]; then
        echo "ERROR: Final TTS audio missing."
        return 1
    fi

    return 0
}

# ===========================================================================
# GENERATE SCENES
# ===========================================================================

PARTS=()
TOTAL_DURATION="0"

for ((i=0; i<SCENE_COUNT; i++)); do

    SCENE_NUMBER=$((i + 1))

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
        echo "WARNING: Scene $SCENE_NUMBER has no English text."
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
    echo "SCENE $SCENE_NUMBER / $SCENE_COUNT"
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

    # =======================================================================
    # KOKORO
    # =======================================================================

    echo "Generating Bella voice..."

    generate_audio \
        "$SCENE_TEXT_EN" \
        "$AUDIO" \
        "scene_${i}"

    # =======================================================================
    # AUDIO DURATION
    # =======================================================================

    SCENE_DUR="$(
        ffprobe \
            -v error \
            -show_entries format=duration \
            -of csv=p=0 \
            "$AUDIO"
    )"

    if [ -z "$SCENE_DUR" ]; then
        echo "ERROR: Cannot determine audio duration."
        exit 1
    fi

    echo "Voice duration: ${SCENE_DUR}s"

    # =======================================================================
    # PEXELS
    # =======================================================================

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
                --retry-delay 2 \
                --connect-timeout 15 \
                --max-time 45 \
                -H "Authorization: $PEXELS_KEY" \
                "https://api.pexels.com/videos/search?query=${ENC_QUERY}&orientation=portrait&size=medium&per_page=20" |
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

    # =======================================================================
    # DOWNLOAD VIDEO
    # =======================================================================

    if [ -n "$VIDEO_URL" ]; then

        echo "Downloading Pexels visual..."

        if ! curl -fL \
            --retry 3 \
            --retry-delay 2 \
            --connect-timeout 20 \
            --max-time 180 \
            "$VIDEO_URL" \
            -o "$RAW_VIDEO"; then

            echo "WARNING: Pexels download failed."
            rm -f "$RAW_VIDEO"

        fi

    fi

    # =======================================================================
    # FALLBACK VISUAL
    # =======================================================================

    if [ ! -s "$RAW_VIDEO" ]; then

        echo "WARNING: No Pexels clip available."
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

    # =======================================================================
    # SUBTITLES
    # =======================================================================

    python3 - \
        "$SCENE_TEXT_AR" \
        "$SUB" \
        "$SCENE_DUR" \
        <<'PY'

import sys
import textwrap

text = sys.argv[1].strip()
output = sys.argv[2]
duration = float(sys.argv[3])

words = text.split()

if not words:
    raise SystemExit("Empty subtitle text")

# Keep subtitle chunks readable.
chunks = [
    " ".join(words[i:i + 6])
    for i in range(0, len(words), 6)
]

if not chunks:
    chunks = [text]

chunk_duration = duration / len(chunks)

def timestamp(seconds):

    milliseconds = int(round(seconds * 1000))

    hours = milliseconds // 3600000
    milliseconds %= 3600000

    minutes = milliseconds // 60000
    milliseconds %= 60000

    seconds_int = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds_int:02d},"
        f"{milliseconds:03d}"
    )

with open(
    output,
    "w",
    encoding="utf-8"
) as f:

    for number, chunk in enumerate(chunks, 1):

        start = (number - 1) * chunk_duration
        end = min(
            number * chunk_duration,
            duration
        )

        wrapped = "\n".join(
            textwrap.wrap(
                chunk,
                width=28,
                break_long_words=False,
                break_on_hyphens=False
            )
        )

        f.write(f"{number}\n")
        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )
        f.write(wrapped)
        f.write("\n\n")

PY

    # =======================================================================
    # MOTION
    # =======================================================================

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

    # =======================================================================
    # RENDER
    # =======================================================================

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
# CHECK SCENES
# ===========================================================================

if [ "${#PARTS[@]}" -lt 1 ]; then
    echo "ERROR: No usable scenes."
    exit 1
fi

echo
echo "============================================
