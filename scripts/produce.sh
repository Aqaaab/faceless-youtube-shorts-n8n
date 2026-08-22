#!/usr/bin/env bash
# ============================================================================
# produce.sh
# YouTube Shorts Production Engine
# Compatible with: youtube-shorts-automation-10-daily.json
# TTS: Kokoro / af_bella
# Visuals: Pexels + animated fallback
# Output: 1080x1920 MP4
# Target duration: 45-58 seconds
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

# Hard limits for YouTube Shorts
MIN_DURATION=30
MAX_DURATION=60

# Preferred target.
# Keeping a little safety margin prevents tiny timing differences
# from pushing the final video over 60 seconds.
TARGET_DURATION=55

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
echo "Target        : ${TARGET_DURATION}s"
echo "Allowed       : ${MIN_DURATION}-${MAX_DURATION}s"
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
# PREPARE SHORT SCRIPT
# ============================================================================

SHORT_TEXT_FILE="$WORK/narration_short.txt"

export SCRIPT_TEXT
export SHORT_TEXT_FILE

python3 <<'PY'
import os
import re

text = os.environ["SCRIPT_TEXT"].strip()
out = os.environ["SHORT_TEXT_FILE"]

# Normalize whitespace.
text = re.sub(r"\s+", " ", text).strip()

# Remove obvious markdown/code artifacts.
text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
text = re.sub(r"__(.*?)__", r"\1", text)

text = re.sub(r"\s+", " ", text).strip()

if not text:
    raise SystemExit("ERROR: Empty script after cleanup")

# Approximate safe first pass.
#
# Kokoro narration speed varies slightly depending on punctuation,
# so we intentionally start below the theoretical 55-second limit.
#
# ~125 words is a reasonable Shorts narration starting point.
words = text.split()

MAX_WORDS = 125

if len(words) > MAX_WORDS:
    selected = words[:MAX_WORDS]

    # Prefer ending at punctuation when possible.
    candidate = " ".join(selected)

    matches = list(
        re.finditer(r"[.!?](?:['\"])?(?=\s|$)", candidate)
    )

    if matches:
        # Use the last sentence ending if it isn't too short.
        end = matches[-1].end()
        sentence_candidate = candidate[:end].strip()

        if len(sentence_candidate.split()) >= 70:
            candidate = sentence_candidate

    text = candidate

with open(out, "w", encoding="utf-8") as f:
    f.write(text + "\n")

print(f"Original words : {len(words)}")
print(f"Short words    : {len(text.split())}")
print(f"Short script   : READY")
PY

if [ ! -s "$SHORT_TEXT_FILE" ]; then
    echo "ERROR: Short narration text was not created"
    exit 1
fi

SHORT_SCRIPT="$(cat "$SHORT_TEXT_FILE")"

echo
echo "Short script prepared."
echo "Narration words: $(printf '%s' "$SHORT_SCRIPT" | wc -w)"

# ============================================================================
# TTS FUNCTION
# ============================================================================

AUDIO_FILE="$AUDIO_DIR/narration.wav"

generate_tts() {

    local INPUT_FILE="$1"

    rm -f "$AUDIO_FILE"

    echo
    echo "Generating Kokoro narration..."

    (
        cd "$KOKORO_DIR"

        PYTHONPATH="$FAKE_AUDIO_DIR:${PYTHONPATH:-}" \
        "$KOKORO_BIN" \
            "$INPUT_FILE" \
            "$AUDIO_FILE" \
            --voice "$VOICE" \
            --speed "$SPEED" \
            --lang "$LANG"
    )

    if [ ! -s "$AUDIO_FILE" ]; then
        echo "ERROR: Kokoro did not create audio"
        exit 1
    fi
}

# ============================================================================
# GENERATE AUDIO
# ============================================================================

generate_tts "$SHORT_TEXT_FILE"

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

echo "Initial narration duration: ${DURATION}s"

# ============================================================================
# AUTOMATIC TEXT REDUCTION
# ============================================================================

# If narration is still over the safe limit, progressively reduce the
# number of words and regenerate the narration.
#
# This prevents a 3+ minute script from reaching the rendering stage.

if awk -v d="$DURATION" 'BEGIN { exit !(d > 58) }'; then

    echo
    echo "Narration is too long."
    echo "Automatically shortening script..."

    for ATTEMPT in 1 2 3 4; do

        CURRENT_WORDS="$(
            wc -w < "$SHORT_TEXT_FILE" |
            tr -d ' '
        )"

        NEW_WORDS=$(
            awk \
                -v w="$CURRENT_WORDS" \
                -v d="$DURATION" \
                'BEGIN {
                    n = int(w * 55 / d)
                    if (n >= w) n = w - 10
                    if (n < 65) n = 65
                    print n
                }'
        )

        if [ "$NEW_WORDS" -ge "$CURRENT_WORDS" ]; then
            NEW_WORDS=$((CURRENT_WORDS - 10))
        fi

        if [ "$NEW_WORDS" -lt 50 ]; then
            NEW_WORDS=50
        fi

        echo "Attempt $ATTEMPT:"
        echo "  Current words : $CURRENT_WORDS"
        echo "  New words     : $NEW_WORDS"

        export SHORT_SCRIPT
        export NEW_WORDS
        export SHORT_TEXT_FILE

        python3 <<'PY'
import os
import re

path = os.environ["SHORT_TEXT_FILE"]
new_words = int(os.environ["NEW_WORDS"])

with open(path, "r", encoding="utf-8") as f:
    text = f.read().strip()

words = text.split()

selected = words[:new_words]
candidate = " ".join(selected)

# Prefer a clean sentence ending.
matches = list(
    re.finditer(r"[.!?](?:['\"])?(?=\s|$)", candidate)
)

if matches:
    end = matches[-1].end()
    clean = candidate[:end].strip()

    if len(clean.split()) >= 50:
        candidate = clean

with open(path, "w", encoding="utf-8") as f:
    f.write(candidate + "\n")

print(f"Updated words: {len(candidate.split())}")
PY

        generate_tts "$SHORT_TEXT_FILE"

        DURATION="$(
            ffprobe \
                -v error \
                -show_entries format=duration \
                -of csv=p=0 \
                "$AUDIO_FILE"
        )"

        echo "  New duration : ${DURATION}s"

        if awk -v d="$DURATION" 'BEGIN { exit !(d <= 58) }'; then
            echo "Narration duration: ACCEPTED"
            break
        fi

        if [ "$ATTEMPT" = "4" ]; then
            echo "ERROR: Could not reduce narration below 58 seconds"
            exit 1
        fi
    done
fi

# ============================================================================
# FINAL AUDIO DURATION CHECK
# ============================================================================

if ! awk -v d="$DURATION" \
    'BEGIN { exit !(d >= 30 && d <= 58) }'; then

    echo
    echo "ERROR: Narration duration is invalid."
    echo "Duration: ${DURATION}s"
    echo "Required: 30-58s"
    exit 1
fi

echo
echo "Narration duration: ${DURATION}s"
echo "Audio: READY"

# ============================================================================
# ARABIC SUBTITLE
# ============================================================================

SUBTITLE="$WORK/subtitles.srt"

SUBTITLE_TEXT="$(jq -r '.subtitle_ar // .text_ar // ""' "$JOB")"

if [ -z "$SUBTITLE_TEXT" ] || [ "$SUBTITLE_TEXT" = "null" ]; then
    SUBTITLE_TEXT="$SHORT_SCRIPT"
else

    # Keep Arabic subtitle approximately synchronized with the shortened
    # narration instead of leaving the original long Arabic text.
    ORIGINAL_SCRIPT_WORDS="$(printf '%s' "$SCRIPT_TEXT" | wc -w | tr -d ' ')"
    SHORT_SCRIPT_WORDS="$(printf '%s' "$SHORT_SCRIPT" | wc -w | tr -d ' ')"

    if [ "$ORIGINAL_SCRIPT_WORDS" -gt 0 ]; then

        export SUBTITLE_TEXT
        export ORIGINAL_SCRIPT_WORDS
        export SHORT_SCRIPT_WORDS

        SUBTITLE_TEXT="$(
            python3 <<'PY'
import os

text = os.environ["SUBTITLE_TEXT"].strip()
original_words = int(os.environ["ORIGINAL_SCRIPT_WORDS"])
short_words = int(os.environ["SHORT_SCRIPT_WORDS"])

words = text.split()

if not words:
    print("")
    raise SystemExit

ratio = short_words / max(original_words, 1)

target = int(len(words) * ratio)

# Keep enough Arabic text to cover the shortened narration.
target = max(1, min(len(words), target + 2))

print(" ".join(words[:target]))
PY
        )"
    fi
fi

if [ -z "$SUBTITLE_TEXT" ]; then
    SUBTITLE_TEXT="$SHORT_SCRIPT"
fi

export SUBTITLE_TEXT
export DURATION
export SUBTITLE

python3 <<'PY'
import os

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
