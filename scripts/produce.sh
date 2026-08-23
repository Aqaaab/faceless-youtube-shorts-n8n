#!/usr/bin/env bash
# ============================================================================
# produce.sh
# YouTube Shorts Production Engine
# English text + English voice + subtitles + Pexels visuals
# No ads for now
# ============================================================================

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUN_DIR="${RUN_DIR:-$ROOT_DIR/run}"
ASSETS_DIR="${ASSETS_DIR:-$ROOT_DIR/assets}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/output}"

JOB_FILE="${JOB_FILE:-$RUN_DIR/job.json}"

VOICE="${VOICE:-af_bella}"
FPS="${FPS:-30}"
WIDTH="${WIDTH:-1080}"
HEIGHT="${HEIGHT:-1920}"

mkdir -p "$RUN_DIR" "$ASSETS_DIR" "$OUTPUT_DIR"

log() {
    printf '[produce] %s\n' "$*"
}

die() {
    printf '[produce] ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    rm -rf "$RUN_DIR/work" 2>/dev/null || true
}

trap cleanup EXIT

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

require_cmd ffmpeg
require_cmd ffprobe
require_cmd python3

[[ -f "$JOB_FILE" ]] || die "Job file not found: $JOB_FILE"

WORK_DIR="$RUN_DIR/work"
SCENES_DIR="$WORK_DIR/scenes"
AUDIO_DIR="$WORK_DIR/audio"
VIDEO_DIR="$WORK_DIR/video"

mkdir -p "$SCENES_DIR" "$AUDIO_DIR" "$VIDEO_DIR"

log "Checking job.json..."

python3 - "$JOB_FILE" <<'PY'
import json
import sys

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

if not isinstance(data, dict):
    raise SystemExit("job.json must contain an object")

scenes = data.get("scenes")

if not isinstance(scenes, list) or not scenes:
    raise SystemExit("job.json must contain a non-empty scenes array")

for i, scene in enumerate(scenes, 1):
    if not isinstance(scene, dict):
        raise SystemExit(f"Scene {i} is not an object")

    text = (
        scene.get("text_en")
        or scene.get("text")
        or scene.get("script")
        or ""
    ).strip()

    if not text:
        raise SystemExit(f"Scene {i} has no English text")

print(f"Valid scenes: {len(scenes)}")
PY

# ============================================================================
# 1. Extract English scenes
# ============================================================================

log "Preparing English scenes..."

python3 - "$JOB_FILE" "$WORK_DIR/scenes.json" <<'PY'
import json
import sys

src = sys.argv[1]
dst = sys.argv[2]

with open(src, "r", encoding="utf-8") as f:
    data = json.load(f)

result = []

for i, scene in enumerate(data["scenes"], 1):
    text = (
        scene.get("text_en")
        or scene.get("text")
        or scene.get("script")
        or ""
    ).strip()

    query = (
        scene.get("pexels_query")
        or scene.get("query")
        or scene.get("visual")
        or "cinematic background"
    ).strip()

    result.append({
        "id": i,
        "text": text,
        "query": query
    })

with open(dst, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
PY

SCENE_COUNT="$(python3 - "$WORK_DIR/scenes.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    print(len(json.load(f)))
PY
)"

# ============================================================================
# 2. Generate one audio file per scene
# ============================================================================

generate_voice() {
    local text="$1"
    local output="$2"

    if command -v kokoro-tts >/dev/null 2>&1; then
        kokoro-tts "$text" \
            --voice "$VOICE" \
            --output "$output"
        return 0
    fi

    if command -v kokoro >/dev/null 2>&1; then
        kokoro "$text" \
            --voice "$VOICE" \
            --output "$output"
        return 0
    fi

    if python3 -c "import kokoro" >/dev/null 2>&1; then
        python3 - "$text" "$output" "$VOICE" <<'PY'
import sys

text = sys.argv[1]
output = sys.argv[2]
voice_name = sys.argv[3]

from kokoro import KPipeline
import soundfile as sf

pipeline = KPipeline(lang_code="a")

samples = []

for _, _, audio in pipeline(text, voice=voice_name):
    samples.append(audio)

if not samples:
    raise RuntimeError("Kokoro generated no audio")

import numpy as np

audio = np.concatenate(samples)

sf.write(
    output,
    audio,
    24000,
    subtype="PCM_16"
)
PY
        return 0
    fi

    die "Kokoro TTS is not installed or available"
}

log "Generating English voice..."

python3 - "$WORK_DIR/scenes.json" "$AUDIO_DIR" <<'PY'
import json
import sys
from pathlib import Path

with open(sys.argv[1], encoding="utf-8") as f:
    scenes = json.load(f)

out = Path(sys.argv[2])

for scene in scenes:
    p = out / f"scene_{scene['id']:03d}.txt"
    p.write_text(scene["text"], encoding="utf-8")
PY

while IFS= read -r scene_id; do
    TEXT_FILE="$AUDIO_DIR/scene_${scene_id}.txt"
    AUDIO_FILE="$AUDIO_DIR/scene_${scene_id}.wav"

    TEXT="$(cat "$TEXT_FILE")"

    log "Voice scene $scene_id"

    generate_voice "$TEXT" "$AUDIO_FILE"

    [[ -s "$AUDIO_FILE" ]] || die "Audio generation failed for scene $scene_id"

done < <(
    python3 - "$WORK_DIR/scenes.json" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as f:
    scenes = json.load(f)

for s in scenes:
    print(s["id"])
PY
)

# ============================================================================
# 3. Create complete voice track
# ============================================================================

log "Combining all voice files..."

CONCAT_FILE="$AUDIO_DIR/audio_concat.txt"

: > "$CONCAT_FILE"

for ((i=1; i<=SCENE_COUNT; i++)); do
    AUDIO_FILE="$AUDIO_DIR/scene_$(printf '%03d' "$i").wav"

    [[ -f "$AUDIO_FILE" ]] || die "Missing audio: $AUDIO_FILE"

    printf "file '%s'\n" "$AUDIO_FILE" >> "$CONCAT_FILE"
done

ffmpeg -y \
    -f concat \
    -safe 0 \
    -i "$CONCAT_FILE" \
    -c:a pcm_s16le \
    "$WORK_DIR/all_voice.wav"

[[ -s "$WORK_DIR/all_voice.wav" ]] || die "Complete voice file was not created"

# ============================================================================
# 4. Calculate scene timings
# ============================================================================

log "Calculating scene timings..."

python3 - "$WORK_DIR/scenes.json" "$AUDIO_DIR" "$WORK_DIR/timings.json" <<'PY'
import json
import subprocess
import sys

scenes_file = sys.argv[1]
audio_dir = sys.argv[2]
output = sys.argv[3]

with open(scenes_file, encoding="utf-8") as f:
    scenes = json.load(f)

timeline = []
current = 0.0

for scene in scenes:
    audio = f"{audio_dir}/scene_{scene['id']:03d}.wav"

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio
        ],
        capture_output=True,
        text=True,
        check=True
    )

    duration = float(result.stdout.strip())

    start = current
    end = current + duration

    timeline.append({
        "id": scene["id"],
        "text": scene["text"],
        "query": scene["query"],
        "start": start,
        "end": end,
        "duration": duration
    })

    current = end

with open(output, "w", encoding="utf-8") as f:
    json.dump(
        {
            "duration": current,
            "scenes": timeline
        },
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"Total duration: {current:.2f}s")
PY

TOTAL_DURATION="$(python3 - "$WORK_DIR/timings.json" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

print(data["duration"])
PY
)"

# ============================================================================
# 5. Generate subtitle file
# ============================================================================

log "Creating English subtitles..."

python3 - "$WORK_DIR/timings.json" "$WORK_DIR/subtitles.ass" <<'PY'
import json
import sys

src = sys.argv[1]
dst = sys.argv[2]

def ass_time(seconds):
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100

    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

with open(src, encoding="utf-8") as f:
    data = json.load(f)

header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

with open(dst, "w", encoding="utf-8") as f:
    f.write(header)

    for scene in data["scenes"]:
        text = scene["text"].replace("\n", " ")
        text = text.replace("{", "\\{").replace("}", "\\}")

        f.write(
            f"Dialogue: 0,{ass_time(scene['start'])},{ass_time(scene['end'])},"
            f"Default,,0,0,0,,{text}\n"
        )
PY

# ============================================================================
# 6. Create visual background
# ============================================================================

log "Creating visual background..."

# If downloaded Pexels clips exist, they can be placed here:
# assets/scene_001.mp4
# assets/scene_002.mp4
# etc.
#
# If they do not exist, a clean animated background is generated automatically.

python3 - "$WORK_DIR/timings.json" "$VIDEO_DIR" "$TOTAL_DURATION" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

timings = sys.argv[1]
out_dir = Path(sys.argv[2])

with open(timings, encoding="utf-8") as f:
    data = json.load(f)

for scene in data["scenes"]:
    i = scene["id"]
    duration = scene["duration"]

    output = out_dir / f"scene_{i:03d}.mp4"

    # Prefer a local Pexels/downloaded video when available.
    possible = [
        Path("assets") / f"scene_{i:03d}.mp4",
        Path("assets") / f"scene_{i}.mp4",
    ]

    source = next((p for p in possible if p.exists()), None)

    if source:
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(source),
            "-t", str(duration),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920",
            "-r", "30",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            str(output)
        ]
    else:
        # Fallback animated dark background.
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i",
            (
                "color=c=black:s=1080x1920:r=30,"
                "format=yuv420p"
            ),
            "-t", str(duration),
            "-vf",
            (
                "zoompan="
                "z='min(zoom+0.0004,1.12)':"
                "d=1:"
                "s=1080x1920:"
                "fps=30"
            ),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            str(output)
        ]

    subprocess.run(cmd, check=True)
PY

# ============================================================================
# 7. Concatenate visual scenes
# ============================================================================

log "Combining visual scenes..."

VIDEO_CONCAT="$VIDEO_DIR/video_concat.txt"

: > "$VIDEO_CONCAT"

for ((i=1; i<=SCENE_COUNT; i++)); do
    FILE="$VIDEO_DIR/scene_$(printf '%03d' "$i").mp4"

    [[ -f "$FILE" ]] || die "Missing visual scene: $FILE"

    printf "file '%s'\n" "$FILE" >> "$VIDEO_CONCAT"
done

ffmpeg -y \
    -f concat \
    -safe 0 \
    -i "$VIDEO_CONCAT" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -pix_fmt yuv420p \
    "$WORK_DIR/background.mp4"

# ============================================================================
# 8. Final Short: video + complete English voice + English subtitles
# ============================================================================

FINAL_FILE="$OUTPUT_DIR/short_$(date +%Y%m%d_%H%M%S).mp4"

log "Rendering final Short..."

ffmpeg -y \
    -i "$WORK_DIR/background.mp4" \
    -i "$WORK_DIR/all_voice.wav" \
    -filter_complex \
    "[0:v]scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=increase,crop=${WIDTH}:${HEIGHT},subtitles='$WORK_DIR/subtitles.ass'[v]" \
    -map "[v]" \
    -map 1:a:0 \
    -c:v libx264 \
    -preset veryfast \
    -crf 20 \
    -r "$FPS" \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 192k \
    -ar 48000 \
    -shortest \
    -movflags +faststart \
    "$FINAL_FILE"

# ============================================================================
# 9. Final validation
# ============================================================================

log "Validating final video..."

[[ -s "$FINAL_FILE" ]] || die "Final video is empty"

VIDEO_INFO="$(
    ffprobe -v error \
    -show_entries stream=codec_type,width,height,r_frame_rate \
    -show_entries format=duration \
    -of default=noprint_wrappers=1 \
    "$FINAL_FILE"
)"

printf '%s\n' "$VIDEO_INFO"

FINAL_DURATION="$(
    ffprobe -v error \
    -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 \
    "$FINAL_FILE"
)"

FINAL_AUDIO="$(
    ffprobe -v error \
    -select_streams a:0 \
    -show_entries stream=codec_name \
    -of default=noprint_wrappers=1:nokey=1 \
    "$FINAL_FILE"
)"

FINAL_VIDEO="$(
    ffprobe -v error \
    -select_streams v:0 \
    -show_entries stream=codec_name \
    -of default=noprint_wrappers=1:nokey=1 \
    "$FINAL_FILE"
)"

[[ "$FINAL_VIDEO" == "h264" ]] || die "Final video codec is not H.264"
[[ "$FINAL_AUDIO" == "aac" ]] || die "Final audio codec is not AAC"

WIDTH_CHECK="$(
    ffprobe -v error \
    -select_streams v:0 \
    -show_entries stream=width \
    -of csv=p=0 \
    "$FINAL_FILE"
)"

HEIGHT_CHECK="$(
    ffprobe -v error \
    -select_streams v:0 \
    -show_entries stream=height \
    -of csv=p=0 \
    "$FINAL_FILE"
)"

[[ "$WIDTH_CHECK" == "$WIDTH" ]] || die "Wrong video width: $WIDTH_CHECK"
[[ "$HEIGHT_CHECK" == "$HEIGHT" ]] || die "Wrong video height: $HEIGHT_CHECK"

python3 - "$FINAL_DURATION" "$TOTAL_DURATION" <<'PY'
import sys

final_duration = float(sys.argv[1])
source_duration = float(sys.argv[2])

difference = abs(final_duration - source_duration)

if difference > 1.0:
    raise SystemExit(
        f"Audio/video duration mismatch: {difference:.2f}s"
    )

print(
    f"Duration check OK: "
    f"source={source_duration:.2f}s "
    f"final={final_duration:.2f}s"
)
PY

# ============================================================================
# Done
# ============================================================================

log "=============================================="
log "SUCCESS"
log "Final video: $FINAL_FILE"
log "Complete voice: $WORK_DIR/all_voice.wav"
log "English subtitles: $WORK_DIR/subtitles.ass"
log "Duration: ${FINAL_DURATION}s"
log "Resolution: ${WIDTH}x${HEIGHT}"
log "=============================================="
