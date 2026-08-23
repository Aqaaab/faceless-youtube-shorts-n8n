#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'


# ============================================================
# YouTube Shorts Production Engine
# ============================================================
#
# Input:
#   <RUN_DIR>/job.json
#
# Output:
#   <RUN_DIR>/video.mp4
#
# Features:
#   - Kokoro TTS
#   - Pexels video
#   - 1080x1920 vertical video
#   - Ken Burns animation
#   - Arabic subtitles
#   - English subtitles
#   - Background music
#   - H.264 video
#   - AAC audio
#   - 30-60 second validation
#
# ============================================================


# ============================================================
# 1. RUN DIRECTORY
# ============================================================

RUN_DIR="${1:-${RUN_DIR:-}}"


if [[ -z "$RUN_DIR" ]]; then

    echo "ERROR: RUN_DIR is required."

    echo "Usage:"
    echo "  $0 <RUN_DIR>"

    exit 2

fi


RUN_DIR="$(realpath -m "$RUN_DIR")"


JOB_JSON="$RUN_DIR/job.json"


if [[ ! -f "$JOB_JSON" ]]; then

    echo "ERROR: Missing job.json:"
    echo "$JOB_JSON"

    exit 1

fi


# ============================================================
# 2. PATH
# ============================================================

export PATH="${HOME}/.local/bin:${PATH}"


# ============================================================
# 3. REQUIRED COMMANDS
# ============================================================

for bin in \
    ffmpeg \
    ffprobe \
    jq \
    curl \
    awk \
    sed \
    realpath
do

    if ! command -v "$bin" >/dev/null 2>&1; then

        echo "ERROR: Required command not found: $bin"

        exit 1

    fi

done


# ============================================================
# 4. REQUIRED ENVIRONMENT
# ============================================================

PEXELS_API_KEY="${PEXELS_API_KEY:-}"


if [[ -z "$PEXELS_API_KEY" ]]; then

    echo "ERROR: PEXELS_API_KEY is not set."

    exit 1

fi


# ============================================================
# 5. DIRECTORIES
# ============================================================

mkdir -p \
    "$RUN_DIR/scenes" \
    "$RUN_DIR/audio" \
    "$RUN_DIR/video" \
    "$RUN_DIR/subtitles" \
    "$RUN_DIR/downloads" \
    "$RUN_DIR/music"


# ============================================================
# 6. JOB SETTINGS
# ============================================================

VOICE="$(
    jq -r '.voice // "af_bella"' "$JOB_JSON"
)"


SPEED="$(
    jq -r '.speed // 1.0' "$JOB_JSON"
)"


LANG_CODE="$(
    jq -r '.lang // "en-us"' "$JOB_JSON"
)"


MUSIC_ENABLED="$(
    jq -r '
        if .music == false then
            "false"
        else
            "true"
        end
    ' "$JOB_JSON"
)"


MUSIC_VOLUME="$(
    jq -r '.music_volume // 0.10' "$JOB_JSON"
)"


ANIMATION_ENABLED="$(
    jq -r '
        if .animation == false then
            "false"
        else
            "true"
        end
    ' "$JOB_JSON"
)"


ADS_ENABLED="$(
    jq -r '
        if .ads == true then
            "true"
        else
            "false"
        end
    ' "$JOB_JSON"
)"


# ============================================================
# 7. ADS
# ============================================================

if [[ "$ADS_ENABLED" == "true" ]]; then

    echo "ERROR: Ads are disabled in this production engine."

    exit 1

fi


# ============================================================
# 8. VALIDATE SPEED
# ============================================================

if ! awk \
    -v speed="$SPEED" \
    'BEGIN {
        exit !(speed >= 0.5 && speed <= 2.0)
    }'
then

    echo "ERROR: SPEED must be between 0.5 and 2.0."

    exit 1

fi


# ============================================================
# 9. VALIDATE MUSIC VOLUME
# ============================================================

if ! awk \
    -v volume="$MUSIC_VOLUME" \
    'BEGIN {
        exit !(volume >= 0 && volume <= 1)
    }'
then

    echo "ERROR: MUSIC_VOLUME must be between 0 and 1."

    exit 1

fi


# ============================================================
# 10. SCENE COUNT
# ============================================================

SCENE_COUNT="$(
    jq '.scenes | length' "$JOB_JSON"
)"


if ! [[ "$SCENE_COUNT" =~ ^[0-9]+$ ]]; then

    echo "ERROR: Invalid scene count."

    exit 1

fi


if (( SCENE_COUNT < 1 )); then

    echo "ERROR: No scenes found in job.json."

    exit 1

fi


# ============================================================
# 11. KOKORO BINARY
# ============================================================

KOKORO_BIN="${KOKORO_BIN:-}"


if [[ -z "$KOKORO_BIN" ]]; then

    if command -v kokoro-tts >/dev/null 2>&1; then

        KOKORO_BIN="$(command -v kokoro-tts)"

    fi

fi


if [[ -z "$KOKORO_BIN" ]]; then

    echo "ERROR: kokoro-tts CLI was not found."

    exit 1

fi


if [[ ! -x "$KOKORO_BIN" ]]; then

    echo "ERROR: Kokoro binary is not executable:"
    echo "$KOKORO_BIN"

    exit 1

fi


# ============================================================
# 12. KOKORO MODEL PATHS
# ============================================================

KOKORO_PATH="${KOKORO_PATH:-}"


KOKORO_MODEL="${KOKORO_MODEL:-}"


KOKORO_VOICES="${KOKORO_VOICES:-}"


if [[ -z "$KOKORO_MODEL" ]]; then

    if [[ -n "$KOKORO_PATH" ]] &&
       [[ -f "$KOKORO_PATH/kokoro-v1.0.onnx" ]]; then

        KOKORO_MODEL="$KOKORO_PATH/kokoro-v1.0.onnx"

    elif [[ -f "$GITHUB_WORKSPACE/kokoro-models/kokoro-v1.0.onnx" ]]; then

        KOKORO_MODEL="$GITHUB_WORKSPACE/kokoro-models/kokoro-v1.0.onnx"

    elif [[ -f "$PWD/kokoro-models/kokoro-v1.0.onnx" ]]; then

        KOKORO_MODEL="$PWD/kokoro-models/kokoro-v1.0.onnx"

    fi

fi


if [[ -z "$KOKORO_VOICES" ]]; then

    if [[ -n "$KOKORO_PATH" ]] &&
       [[ -f "$KOKORO_PATH/voices-v1.0.bin" ]]; then

        KOKORO_VOICES="$KOKORO_PATH/voices-v1.0.bin"

    elif [[ -f "$GITHUB_WORKSPACE/kokoro-models/voices-v1.0.bin" ]]; then

        KOKORO_VOICES="$GITHUB_WORKSPACE/kokoro-models/voices-v1.0.bin"

    elif [[ -f "$PWD/kokoro-models/voices-v1.0.bin" ]]; then

        KOKORO_VOICES="$PWD/kokoro-models/voices-v1.0.bin"

    fi

fi


if [[ -z "$KOKORO_MODEL" ]]; then

    echo "ERROR: KOKORO_MODEL was not found."

    exit 1

fi


if [[ -z "$KOKORO_VOICES" ]]; then

    echo "ERROR: KOKORO_VOICES was not found."

    exit 1

fi


if [[ ! -s "$KOKORO_MODEL" ]]; then

    echo "ERROR: Kokoro model does not exist:"
    echo "$KOKORO_MODEL"

    exit 1

fi


if [[ ! -s "$KOKORO_VOICES" ]]; then

    echo "ERROR: Kokoro voices do not exist:"
    echo "$KOKORO_VOICES"

    exit 1

fi


export KOKORO_MODEL
export KOKORO_VOICES


echo
echo "======================================"
echo "KOKORO CONFIGURATION"
echo "======================================"

echo "Binary:"
echo "$KOKORO_BIN"

echo "Model:"
echo "$KOKORO_MODEL"

echo "Voices:"
echo "$KOKORO_VOICES"

echo "Voice:"
echo "$VOICE"

echo "Speed:"
echo "$SPEED"

echo "Language:"
echo "$LANG_CODE"


# ============================================================
# 13. DURATION
# ============================================================

duration() {

    local file="$1"


    if [[ ! -s "$file" ]]; then

        echo "ERROR: Cannot measure missing file:"
        echo "$file"

        return 1

    fi


    ffprobe \
        -v error \
        -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 \
        "$file" |
        awk '
            {
                if ($1 == "" || $1 == "N/A") {
                    exit 1
                }

                printf "%.3f", $1
            }
        '

}


# ============================================================
# 14. KOKORO TTS
# ============================================================

run_kokoro() {

    local text_file="$1"

    local output_file="$2"

    local log_file="${output_file}.kokoro.log"

    local tmp_file="${output_file}.tmp.wav"


    rm -f \
        "$output_file" \
        "$tmp_file" \
        "$log_file"


    echo
    echo "--------------------------------------"
    echo "[KOKORO]"
    echo "Input : $text_file"
    echo "Output: $output_file"
    echo "Voice : $VOICE"
    echo "Speed : $SPEED"
    echo "Lang  : $LANG_CODE"
    echo "Model : $KOKORO_MODEL"
    echo "Voices: $KOKORO_VOICES"
    echo "--------------------------------------"


    "$KOKORO_BIN" \
        "$text_file" \
        "$tmp_file" \
        --voice "$VOICE" \
        --speed "$SPEED" \
        --lang "$LANG_CODE" \
        --model "$KOKORO_MODEL" \
        --voices "$KOKORO_VOICES" \
        2>&1 |
        tee "$log_file"


    if [[ ! -s "$tmp_file" ]]; then

        echo "ERROR: Kokoro produced no audio."

        cat "$log_file" >&2 || true

        return 1

    fi


    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -i "$tmp_file" \
        -ar 48000 \
        -ac 2 \
        -c:a pcm_s16le \
        "$output_file"


    rm -f "$tmp_file"


    if [[ ! -s "$output_file" ]]; then

        echo "ERROR: Audio normalization failed."

        return 1

    fi


    duration "$output_file" >/dev/null


    echo "[KOKORO] Audio generated successfully."

    return 0

}


# ============================================================
# 15. GENERATE VOICE
# ============================================================

generate_voice() {

    local text="$1"

    local output="$2"

    local text_file="${output}.txt"


    rm -f \
        "$output" \
        "$text_file"


    if [[ -z "${text//[[:space:]]/}" ]]; then

        echo "ERROR: Empty narration."

        return 1

    fi


    printf '%s\n' "$text" > "$text_file"


    if ! run_kokoro \
        "$text_file" \
        "$output"
    then

        rm -f "$text_file"

        return 1

    fi


    rm -f "$text_file"


    return 0

}


# ============================================================
# 16. PEXELS VIDEO
# ============================================================

pexels_video() {

    local query="$1"

    local index="$2"

    local json_file="$RUN_DIR/downloads/pexels_${index}.json"

    local output_file="$RUN_DIR/downloads/source_${index}.mp4"


    rm -f \
        "$json_file" \
        "$output_file"


    echo
    echo "--------------------------------------"
    echo "[PEXELS]"
    echo "Query: $query"
    echo "--------------------------------------"


    curl \
        -fsSL \
        --retry 5 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 120 \
        -H "Authorization: $PEXELS_API_KEY" \
        --get \
        "https://api.pexels.com/videos/search" \
        --data-urlencode "query=$query" \
        --data-urlencode "orientation=portrait" \
        --data-urlencode "size=medium" \
        --data-urlencode "per_page=15" \
        > "$json_file"


    local url=""


    url="$(
        jq -r '
            [
                .videos[]?
                | .video_files[]?
                | select(.file_type == "video/mp4")
                | select(.link != null)
                | select(.width != null)
                | select(.height != null)
                | {
                    link: .link,
                    width: .width,
                    height: .height,
                    pixels: (.width * .height)
                }
            ]
            | map(
                . + {
                    portrait:
                    (
                        if .height >= .width
                        then 1
                        else 0
                        end
                    )
                }
            )
            | sort_by(
                .portrait,
                .pixels
            )
            | reverse
            | .[0].link // empty
        ' "$json_file"
    )"


    if [[ -z "$url" ]]; then

        echo "ERROR: No usable Pexels video found."

        jq '.' "$json_file" >&2 || true

        return 1

    fi


    echo "[PEXELS] Downloading..."


    curl \
        -fL \
        --retry 5 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 180 \
        -o "$output_file" \
        "$url"


    if [[ ! -s "$output_file" ]]; then

        echo "ERROR: Pexels download is empty."

        return 1

    fi


    if ! ffprobe \
        -v error \
        -select_streams v:0 \
        -show_entries stream=codec_name \
        -of csv=p=0 \
        "$output_file" \
        >/dev/null
    then

        echo "ERROR: Downloaded Pexels video is invalid."

        return 1

    fi


    printf '%s\n' "$output_file"

}


# ============================================================
# 17. CREATE SCENE VIDEO
# ============================================================

make_scene_video() {

    local source="$1"

    local scene_duration="$2"

    local output="$3"


    echo
    echo "--------------------------------------"
    echo "[VIDEO]"
    echo "Source  : $source"
    echo "Duration: ${scene_duration}s"
    echo "Output  : $output"
    echo "--------------------------------------"


    local filter=""


    if [[ "$ANIMATION_ENABLED" == "true" ]]; then

        filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p"

    else

        filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p"

    fi


    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -stream_loop -1 \
        -i "$source" \
        -t "$scene_duration" \
        -vf "$filter" \
        -an \
        -c:v libx264 \
        -preset veryfast \
        -crf 20 \
        -pix_fmt yuv420p \
        -r 30 \
        -movflags +faststart \
        "$output"


    if [[ ! -s "$output" ]]; then

        echo "ERROR: Scene video was not created."

        return 1

    fi

}


# ============================================================
# 18. ASS ESCAPE
# ============================================================

ass_escape() {

    local text="$1"


    text="${text//\\/\\\\}"

    text="${text//\{/\\\{}"

    text="${text//\}/\\\}}"


    printf '%s' "$text"

}


# ============================================================
# 19. ASS TIME
# ============================================================

seconds_to_ass() {

    local seconds="$1"


    awk \
        -v x="$seconds" \
        'BEGIN {

            total = int(x * 100 + 0.5)

            h = int(total / 360000)

            m = int((total % 360000) / 6000)

            s = int((total % 6000) / 100)

            c = total % 100

            printf "%d:%02d:%02d.%02d", \
                h, m, s, c

        }'

}


# ============================================================
# 20. CREATE ASS SUBTITLES
# ============================================================

create_ass() {

    local output="$RUN_DIR/subtitles/subtitles.ass"


    cat > "$output" <<'EOF'
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: EN,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,70,70,900,1
Style: AR,Arial,52,&H0000FFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,280,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
EOF


    local start_time="0"


    for ((i=1; i<=SCENE_COUNT; i++)); do

        local text=""

        local arabic=""

        local scene_duration=""

        local end_time=""

        local start_ass=""

        local end_ass=""

        local en=""

        local ar=""


        text="$(
            jq -r \
                ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" \
                "$JOB_JSON"
        )"


        arabic="$(
            jq -r \
                ".scenes[$((i-1))].text_ar // empty" \
                "$JOB_JSON"
        )"


        if [[ -z "$text" ]]; then

            echo "ERROR: Scene $i missing English subtitle."

            exit 1

        fi


        if [[ -z "$arabic" ]]; then

            echo "ERROR: Scene $i missing Arabic subtitle."

            exit 1

        fi


        scene_duration="$(
            duration "$RUN_DIR/audio/scene_${i}.wav"
        )"


        end_time="$(
            awk \
                -v s="$start_time" \
                -v d="$scene_duration" \
                'BEGIN {
                    printf "%.3f", s+d
                }'
        )"


        start_ass="$(
            seconds_to_ass "$start_time"
        )"


        end_ass="$(
            seconds_to_ass "$end_time"
        )"


        en="$(
            ass_escape "$text"
        )"


        ar="$(
            ass_escape "$arabic"
        )"


        printf \
            'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' \
            "$start_ass" \
            "$end_ass" \
            "$en" \
            >> "$output"


        printf \
            'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' \
            "$start_ass" \
            "$end_ass" \
            "$ar" \
            >> "$output"


        start_time="$end_time"

    done


    printf '%s\n' "$output"

}


# ============================================================
# 21. FIND MUSIC
# ============================================================

find_music() {

    if [[ -n "${MUSIC_FILE:-}" ]] &&
       [[ -f "$MUSIC_FILE" ]]; then

        printf '%s\n' "$MUSIC_FILE"

        return 0

    fi


    local dir="${MUSIC_DIR:-$RUN_DIR/music}"


    if [[ ! -d "$dir" ]]; then

        return 1

    fi


    local file=""


    for file in \
        "$dir"/*.mp3 \
        "$dir"/*.wav \
        "$dir"/*.m4a \
        "$dir"/*.aac
    do

        if [[ -f "$file" ]]; then

            printf '%s\n' "$file"

            return 0

        fi

    done


    return 1

}


# ============================================================
# 22. MIX MUSIC
# ============================================================

add_music() {

    local voice="$1"

    local music="$2"

    local output="$3"

    local volume="$4"


    local voice_duration=""


    voice_duration="$(
        duration "$voice"
    )"


    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -stream_loop -1 \
        -i "$music" \
        -i "$voice" \
        -filter_complex \
        "[0:a]volume=${volume},atrim=0:${voice_duration},asetpts=N/SR/TB[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]" \
        -map "[mix]" \
        -ar 48000 \
        -ac 2 \
        -c:a pcm_s16le \
        "$output"


    if [[ ! -s "$output" ]]; then

        echo "ERROR: Music mix failed."

        return 1

    fi

}


# ============================================================
# 23. CONCAT VIDEO SCENES
# ============================================================

concat_scenes() {

    local list_file="$RUN_DIR/scenes/concat.txt"

    local output="$RUN_DIR/video/visuals.mp4"


    rm -f \
        "$list_file" \
        "$output"


    : > "$list_file"


    for ((i=1; i<=SCENE_COUNT; i++)); do

        local scene="$RUN_DIR/scenes/scene_${i}.mp4"


        if [[ ! -s "$scene" ]]; then

            echo "ERROR: Missing scene video:"
            echo "$scene"

            return 1

        fi


        printf "file '%s'\n" "$scene" >> "$list_file"

    done


    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -f concat \
        -safe 0 \
        -i "$list_file" \
        -an \
        -c:v libx264 \
        -preset veryfast \
        -crf 20 \
        -pix_fmt yuv420p \
        -r 30 \
        -movflags +faststart \
        "$output"


    if [[ ! -s "$output" ]]; then

        echo "ERROR: C
