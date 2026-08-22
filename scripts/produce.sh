#!/usr/bin/env bash
# ============================================================================
# produce.sh
# YouTube Shorts Production Engine
# Compatible with: youtube-shorts-automation-10-daily.json
# TTS: Kokoro / af_bella
# Visuals: Pexels + animated fallback
# Output: 1080x1920 MP4
# ============================================================================

set -euo pipefail

RUN_DIR="${1:-}"

if [ -z "$RUN_DIR" ]; then
    echo "ERROR: Usage: produce.sh <RUN_DIR>"
    exit 1
fi

JOB="$RUN_DIR/job.json"
OUT="$RUN_DIR/video.mp4"

if [ ! -s "$JOB" ]; then
    echo "ERROR: job.json missing: $JOB"
    exit 1
fi

# ============================================================================
# CONFIG
# ============================================================================

VOICE="af_bella"
SPEED="1.0"
LANG="en-us"

PEXELS_KEY="${PEXELS_API_KEY:-}"

WORK="$RUN_DIR/work"
AUDIO_DIR="$WORK/audio"
RAW_DIR="$WORK/raw"
VIDEO_DIR="$WORK/video"

mkdir -p "$WORK" "$AUDIO_DIR" "$RAW_DIR" "$VIDEO_DIR"

echo
echo "============================================================"
echo "          YOUTUBE SHORTS PRODUCTION ENGINE"
echo "============================================================"
echo "Run directory : $RUN_DIR"
echo "Voice         : $VOICE"
echo "Speed         : $SPEED"
echo "Language      : $LANG"
echo "Pexels        : $([ -n "$PEXELS_KEY" ] && echo ENABLED || echo DISABLED)"
echo "Output        : 1080x1920"
echo "============================================================"
echo

# ============================================================================
# DEPENDENCIES
# ============================================================================

for CMD in python3 ffmpeg ffprobe jq curl; do
    if ! command -v "$CMD" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $CMD"
        exit 1
    fi
done

echo "Dependencies: OK"

# ============================================================================
# READ JOB
# ============================================================================

SCRIPT_TEXT="$(jq -r '.script // ""' "$JOB")"
QUERY="$(jq -r '.query // "nature"' "$JOB")"
JOB_VOICE="$(jq -r '.voice // "af_bella"' "$JOB")"

if [ -z "$SCRIPT_TEXT" ] || [ "$SCRIPT_TEXT" = "null" ]; then
    echo "ERROR: job.json does not contain script"
    exit 1
fi

if [ -z "$QUERY" ] || [ "$QUERY" = "null" ]; then
    QUERY="nature"
fi

# Only allow known Kokoro voices from the workflow.
case "$JOB_VOICE" in
    af_bella|af_heart|am_adam|am_michael)
        VOICE="$JOB_VOICE"
        ;;
    *)
        echo "WARNING: Unsupported voice '$JOB_VOICE'. Using af_bella."
        VOICE="af_bella"
        ;;
esac

echo "Script loaded."
echo "Visual query: $QUERY"
echo "Voice: $VOICE"

# ============================================================================
# KOKORO
# ============================================================================

KOKORO_DIR="$RUN_DIR/kokoro"
mkdir -p "$KOKORO_DIR"

echo
echo "Checking Kokoro..."

python3 -m pip install \
    --user \
    --quiet \
    --upgrade \
    kokoro-tts \
    soundfile \
    kokoro-onnx

export PATH="$HOME/.local/bin:$PATH"

KOKORO_BIN="$(command -v kokoro-tts || true)"

if [ -z "$KOKORO_BIN" ]; then
    echo "ERROR: kokoro-tts command not found"
    exit 1
fi

echo "Kokoro: $KOKORO_BIN"

# ============================================================================
# HEADLESS AUDIO COMPATIBILITY
# ============================================================================

FAKE_AUDIO_DIR="$KOKORO_DIR/runtime"

mkdir -p "$FAKE_AUDIO_DIR"

cat > "$FAKE_AUDIO_DIR/sounddevice.py" <<'PY'
class _DummyStream:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def start(self):
        return self

    def stop(self):
        return self

    def close(self):
        return self

    def write(self, *args, **kwargs):
        return None

    def read(self, *args, **kwargs):
        return None


class OutputStream(_DummyStream):
    pass


class InputStream(_DummyStream):
    pass


class RawOutputStream(_DummyStream):
    pass


class RawInputStream(_DummyStream):
    pass


def play(*args, **kwargs):
    return None


def wait(*args, **kwargs):
    return None


def stop(*args, **kwargs):
    return None


def rec(*args, **kwargs):
    return None


def query_devices(*args, **kwargs):
    return []


def check_input_settings(*args, **kwargs):
    return None


def check_output_settings(*args, **kwargs):
    return None


def default(*args, **kwargs):
    return None
PY

export PYTHONPATH="$FAKE_AUDIO_DIR:${PYTHONPATH:-}"

# ============================================================================
# KOKORO MODEL
# ============================================================================

MODEL="$KOKORO_DIR/kokoro-v1.0.onnx"
VOICES="$KOKORO_DIR/voices-v1.0.bin"

MODEL_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"
VOICES_URL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"

if [ ! -s "$MODEL" ]; then
    echo "Downloading Kokoro model..."

    curl -fL \
        --retry 5 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 900 \
        "$MODEL_URL" \
        -o "$MODEL"
fi

if [ ! -s "$VOICES" ]; then
    echo "Downloading Kokoro voices..."

    curl -fL \
        --retry 5 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 300 \
        "$VOICES_URL" \
        -o "$VOICES"
fi

if [ ! -s "$MODEL" ]; then
    echo "ERROR: Kokoro model unavailable"
    exit 1
fi

if [ ! -s "$VOICES" ]; then
    echo "ERROR: Kokoro voices unavailable"
    exit 1
fi

echo "Kokoro model: READY"

# ============================================================================
# TTS
# ============================================================================

TEXT_FILE="$WORK/narration.txt"
AUDIO_FILE="$AUDIO_DIR/narration.wav"

printf '%s\n' "$SCRIPT_TEXT" > "$TEXT_FILE"

echo
echo "Generating Kokoro narration..."

(
    cd "$KOKORO_DIR"

    PYTHONPATH="$FAKE_AUDIO_DIR:${PYTHONPATH:-}" \
    "$KOKORO_BIN" \
        "$TEXT_FILE" \
        "$AUDIO_FILE" \
        --voice "$VOICE" \
        --speed "$SPEED" \
        --lang "$LANG"
)

if [ ! -s "$AUDIO_FILE" ]; then
    echo "ERROR: Kokoro did not create audio"
    exit 1
fi

echo "Audio: READY"

# ============================================================================
# AUDIO DURATION
# ============================================================================

DURATION="$(
    ffprobe \
        -v error \
        -show_entries format=duration \
        -of csv=p=0 \
        "$AUDIO_FILE"
)"

if [ -z "$DURATION" ]; then
    echo "ERROR: Could not determine audio duration"
    exit 1
fi

echo "Narration duration: ${DURATION}s"

# ============================================================================
# ARABIC SUBTITLE
# ============================================================================

SUBTITLE="$WORK/subtitles.srt"

SUBTITLE_TEXT="$(jq -r '.subtitle_ar // .text_ar // ""' "$JOB")"

if [ -z "$SUBTITLE_TEXT" ] || [ "$SUBTITLE_TEXT" = "null" ]; then
    SUBTITLE_TEXT="$SCRIPT_TEXT"
fi

export SUBTITLE_TEXT
export DURATION
export SUBTITLE

python3 <<'PY'
import os
import re

text = os.environ["SUBTITLE_TEXT"].strip()
duration = float(os.environ["DURATION"])
out = os.environ["SUBTITLE"]

words = text.split()

if not words:
    raise SystemExit("Empty subtitle text")

chunks = []

for i in range(0, len(words), 5):
    chunks.append(" ".join(words[i:i+5]))

if not chunks:
    raise SystemExit("No subtitle chunks")

chunk_duration = duration / len(chunks)

def timestamp(seconds):
    total_ms = int(round(seconds * 1000))

    hours = total_ms // 3600000
    total_ms %= 3600000

    minutes = total_ms // 60000
    total_ms %= 60000

    seconds_part = total_ms // 1000
    milliseconds = total_ms % 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds_part:02d},"
        f"{milliseconds:03d}"
    )

with open(out, "w", encoding="utf-8") as f:

    for number, chunk in enumerate(chunks, 1):

        start = (number - 1) * chunk_duration
        end = min(number * chunk_duration, duration)

        # Simple Arabic-friendly line wrapping.
        lines = []

        current = ""

        for word in chunk.split():
            candidate = f"{current} {word}".strip()

            if len(candidate) > 28 and current:
                lines.append(current)
                current = word
            else:
                current = candidate

        if current:
            lines.append(current)

        display = "\n".join(lines)

        f.write(f"{number}\n")
        f.write(
            f"{timestamp(start)} --> "
            f"{timestamp(end)}\n"
        )
        f.write(display)
        f.write("\n\n")
PY

if [ ! -s "$SUBTITLE" ]; then
    echo "ERROR: Subtitle generation failed"
    exit 1
fi

echo "Subtitles: READY"

# ============================================================================
# PEXELS
# ============================================================================

RAW_VIDEO="$RAW_DIR/source.mp4"
VIDEO_URL=""

if [ -n "$PEXELS_KEY" ]; then

    ENCODED_QUERY="$(
        printf '%s' "$QUERY" | jq -sRr @uri
    )"

    echo
    echo "Searching Pexels..."

    mapfile -t LINKS < <(
        curl -fsS \
            --retry 3 \
            --retry-delay 2 \
            --connect-timeout 15 \
            --max-time 45 \
            -H "Authorization: $PEXELS_KEY" \
            "https://api.pexels.com/videos/search?query=${ENCODED_QUERY}&orientation=portrait&size=medium&per_page=20" |
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
        VIDEO_URL="${LINKS[0]}"
        echo "Pexels result found."
    else
        echo "No suitable Pexels result."
    fi
else
    echo
    echo "Pexels disabled."
fi

# ============================================================================
# DOWNLOAD PEXELS
# ============================================================================

if [ -n "$VIDEO_URL" ]; then

    echo "Downloading Pexels video..."

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

# ============================================================================
# FALLBACK GRAPHICS
# ============================================================================

if [ ! -s "$RAW_VIDEO" ]; then

    echo
    echo "Creating animated fallback background..."

    ffmpeg -y \
        -hide_banner \
        -loglevel error \
        -f lavfi \
        -i "color=c=0x101827:s=1080x1920:r=30" \
        -t "$DURATION" \
        -vf "
drawbox=x=60:y=180:w=960:h=1560:color=0x172554@0.90:t=fill,
drawbox=x='100+80*sin(2*PI*t/6)':y='400+120*cos(2*PI*t/5)':w=300:h=300:color=0x2563eb@0.28:t=fill,
drawbox=x='620+70*cos(2*PI*t/7)':y='1050+100*sin(2*PI*t/6)':w=300:h=300:color=0x7c3aed@0.25:t=fill
" \
        -pix_fmt yuv420p \
        -c:v libx264 \
        -preset veryfast \
        -crf 24 \
        "$RAW_VIDEO"
fi

if [ ! -s "$RAW_VIDEO" ]; then
    echo "ERROR: Could not create visual"
    exit 1
fi

echo "Visual: READY"

# ============================================================================
# RENDER
# ============================================================================

FINAL_SCENE="$VIDEO_DIR/final.mp4"

echo
echo "Rendering 1080x1920 Shorts video..."

CAPTION_STYLE="FontName=DejaVu Sans,Fontsize=20,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=4,Shadow=2,Alignment=2,MarginV=300"

ffmpeg -y \
    -hide_banner \
    -loglevel error \
    -stream_loop -1 \
    -i "$RAW_VIDEO" \
    -i "$AUDIO_FILE" \
    -t "$DURATION" \
    -filter_complex "
[0:v]
scale=1180:2098:force_original_aspect_ratio=increase,
crop=1080:1920,
setsar=1,
eq=brightness=-0.035:saturation=1.08,
zoompan=z='min(zoom+0.0005,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,
subtitles='${SUBTITLE}':force_style='${CAPTION_STYLE}'
[v]
" \
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
    echo "ERROR: Rendering failed"
    exit 1
fi

# ============================================================================
# FINAL COPY
# ============================================================================

cp "$FINAL_SCENE" "$OUT"

if [ ! -s "$OUT" ]; then
    echo "ERROR: Final video missing"
    exit 1
fi

# ============================================================================
# VERIFY
# ============================================================================

FINAL_DURATION="$(
    ffprobe \
        -v error \
        -show_entries format=duration \
        -of csv=p=0 \
        "$OUT"
)"

WIDTH="$(
    ffprobe \
        -v error \
        -select_streams v:0 \
        -show_entries stream=width \
        -of csv=p=0 \
        "$OUT"
)"

HEIGHT="$(
    ffprobe \
        -v error \
        -select_streams v:0 \
        -show_entries stream=height \
        -of csv=p=0 \
        "$OUT"
)"

VIDEO_CODEC="$(
    ffprobe \
        -v error \
        -select_streams v:0 \
        -show_entries stream=codec_name \
        -of csv=p=0 \
        "$OUT"
)"

AUDIO_CODEC="$(
    ffprobe \
        -v error \
        -select_streams a:0 \
        -show_entries stream=codec_name \
        -of csv=p=0 \
        "$OUT"
)"

echo
echo "============================================================"
echo "                  FINAL VIDEO READY"
echo "============================================================"
echo "Output       : $OUT"
echo "Width        : $WIDTH"
echo "Height       : $HEIGHT"
echo "Duration     : ${FINAL_DURATION}s"
echo "Video codec  : $VIDEO_CODEC"
echo "Audio codec  : $AUDIO_CODEC"
echo "Voice        : Kokoro $VOICE"
echo "Pexels       : $([ -n "$PEXELS_KEY" ] && echo ENABLED || echo DISABLED)"
echo "Subtitles    : ENABLED"
echo "============================================================"

# ============================================================================
# HARD VALIDATION
# ============================================================================

if [ "$WIDTH" != "1080" ] || [ "$HEIGHT" != "1920" ]; then
    echo "ERROR: Final resolution is not 1080x1920"
    exit 1
fi

if ! awk -v d="$FINAL_DURATION" 'BEGIN { exit !(d >= 30 && d <= 60) }'; then
    echo "ERROR: Final duration is outside 30-60 seconds"
    exit 1
fi

if [ "$VIDEO_CODEC" != "h264" ]; then
    echo "ERROR: Video codec is not H.264"
    exit 1
fi

if [ "$AUDIO_CODEC" != "aac" ]; then
    echo "ERROR: Audio codec is not AAC"
    exit 1
fi

echo "VALIDATION: PASS"
echo "VIDEO: $OUT"

printf \
'{"video":"%s","duration":%s,"width":%s,"height":%s,"voice":"%s","videoCodec":"%s","audioCodec":"%s"}\n' \
"$OUT" \
"$FINAL_DURATION" \
"$WIDTH" \
"$HEIGHT" \
"$VOICE" \
"$VIDEO_CODEC" \
"$AUDIO_CODEC"
