#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${1:-${RUN_DIR:-}}"

if [[ -z "$RUN_DIR" ]]; then
    echo "ERROR: Usage: $0 <RUN_DIR>" >&2
    exit 2
fi

RUN_DIR="$(realpath -m "$RUN_DIR")"
JOB_JSON="$RUN_DIR/job.json"

if [[ ! -f "$JOB_JSON" ]]; then
    echo "ERROR: Missing $JOB_JSON" >&2
    exit 1
fi

export PATH="${HOME}/.local/bin:${PATH}"

for bin in ffmpeg ffprobe jq curl awk sed realpath; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $bin" >&2
        exit 1
    fi
done

PEXELS_API_KEY="${PEXELS_API_KEY:-}"

if [[ -z "$PEXELS_API_KEY" ]]; then
    echo "ERROR: PEXELS_API_KEY is not set." >&2
    exit 1
fi

mkdir -p \
    "$RUN_DIR/scenes" \
    "$RUN_DIR/audio" \
    "$RUN_DIR/video" \
    "$RUN_DIR/subtitles" \
    "$RUN_DIR/downloads" \
    "$RUN_DIR/music"

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

if [[ "$ADS_ENABLED" != "false" ]]; then
    echo "ERROR: Ads are disabled in this production engine." >&2
    exit 1
fi

if ! awk -v x="$SPEED" 'BEGIN { exit !(x >= 0.5 && x <= 2.0) }'; then
    echo "ERROR: SPEED must be between 0.5 and 2.0." >&2
    exit 1
fi

if ! awk -v x="$MUSIC_VOLUME" 'BEGIN { exit !(x >= 0 && x <= 1) }'; then
    echo "ERROR: MUSIC_VOLUME must be between 0 and 1." >&2
    exit 1
fi

SCENE_COUNT="$(
    jq -r '
        if (.scenes | type) == "array"
        then (.scenes | length)
        else 0
        end
    ' "$JOB_JSON"
)"

if ! [[ "$SCENE_COUNT" =~ ^[0-9]+$ ]] || (( SCENE_COUNT < 1 )); then
    echo "ERROR: No scenes found in job.json." >&2
    exit 1
fi

KOKORO_BIN="${KOKORO_BIN:-}"

if [[ -z "$KOKORO_BIN" ]]; then
    if command -v kokoro-tts >/dev/null 2>&1; then
        KOKORO_BIN="$(command -v kokoro-tts)"
    fi
fi

if [[ -z "$KOKORO_BIN" ]]; then
    echo "ERROR: kokoro-tts CLI was not found." >&2
    exit 1
fi

if [[ ! -x "$KOKORO_BIN" ]]; then
    echo "ERROR: Kokoro binary is not executable: $KOKORO_BIN" >&2
    exit 1
fi

KOKORO_PATH="${KOKORO_PATH:-}"

if [[ -z "$KOKORO_PATH" ]]; then

    if [[ -f "$PWD/kokoro-models/kokoro-v1.0.onnx" ]]; then
        KOKORO_PATH="$PWD/kokoro-models"

    elif [[ -n "${GITHUB_WORKSPACE:-}" ]] &&
         [[ -f "$GITHUB_WORKSPACE/kokoro-models/kokoro-v1.0.onnx" ]]; then
        KOKORO_PATH="$GITHUB_WORKSPACE/kokoro-models"

    elif [[ -f "$PWD/kokoro-v1.0.onnx" ]]; then
        KOKORO_PATH="$PWD"
    fi
fi

if [[ -z "$KOKORO_PATH" ]]; then
    echo "ERROR: KOKORO_PATH was not found." >&2
    exit 1
fi

export KOKORO_PATH

MODEL_FILE="$KOKORO_PATH/kokoro-v1.0.onnx"
VOICES_FILE="$KOKORO_PATH/voices-v1.0.bin"

if [[ ! -s "$MODEL_FILE" ]]; then
    echo "ERROR: Missing Kokoro model: $MODEL_FILE" >&2
    exit 1
fi

if [[ ! -s "$VOICES_FILE" ]]; then
    echo "ERROR: Missing Kokoro voices: $VOICES_FILE" >&2
    exit 1
fi

duration() {

    local file="$1"

    if [[ ! -s "$file" ]]; then
        echo "ERROR: Cannot measure $file" >&2
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

run_kokoro() {

    local text_file="$1"
    local output_file="$2"

    local tmp="${output_file}.tmp.wav"
    local log="${output_file}.kokoro.log"

    rm -f \
        "$output_file" \
        "$tmp" \
        "$log"

    echo "--------------------------------------"
    echo "[KOKORO]"
    echo "Input : $text_file"
    echo "Output: $output_file"
    echo "Voice : $VOICE"
    echo "Speed : $SPEED"
    echo "Lang  : $LANG_CODE"
    echo "Model : $KOKORO_PATH"
    echo "--------------------------------------"

    if "$KOKORO_BIN" \
        "$text_file" \
        "$tmp" \
        --voice "$VOICE" \
        --speed "$SPEED" \
        --lang "$LANG_CODE" \
        --debug \
        2>&1 |
        tee "$log"
    then
        :
    else
        echo "ERROR: Kokoro failed." >&2
        cat "$log" >&2 || true
        rm -f "$tmp"
        return 1
    fi

    if [[ ! -s "$tmp" ]]; then
        echo "ERROR: Kokoro produced no audio." >&2
        cat "$log" >&2 || true
        return 1
    fi

    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -i "$tmp" \
        -ar 48000 \
        -ac 2 \
        -c:a pcm_s16le \
        "$output_file"

    rm -f "$tmp"

    if [[ ! -s "$output_file" ]]; then
        echo "ERROR: Audio normalization failed." >&2
        return 1
    fi
}

generate_voice() {

    local text="$1"
    local output="$2"

    local txt="${output}.txt"

    rm -f \
        "$output" \
        "$txt"

    if [[ -z "${text//[[:space:]]/}" ]]; then
        echo "ERROR: Empty narration." >&2
        return 1
    fi

    printf '%s\n' "$text" > "$txt"

    run_kokoro \
        "$txt" \
        "$output"

    local rc=$?

    rm -f "$txt"

    return "$rc"
}

pexels_video() {

    local query="$1"
    local index="$2"

    local json="$RUN_DIR/downloads/pexels_${index}.json"
    local out="$RUN_DIR/downloads/source_${index}.mp4"

    rm -f \
        "$json" \
        "$out"

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
        --data-urlencode "per_page=20" \
        > "$json"

    local url

    url="$(
        jq -r '
            [
                .videos[]?
                | .video_files[]?
                | select(.file_type == "video/mp4")
                | select(.link != null)
                | select(.width != null and .height != null)
                | {
                    link: .link,
                    width: .width,
                    height: .height,
                    pixels: (.width * .height),
                    portrait: (
                        if .height > .width
                        then 1
                        else 0
                        end
                    )
                }
            ]
            | sort_by(.portrait, .pixels)
            | reverse
            | .[0].link // empty
        ' "$json"
    )"

    if [[ -z "$url" ]]; then
        echo "ERROR: No usable Pexels video for query: $query" >&2
        return 1
    fi

    echo "[PEXELS] Downloading..."

    curl \
        -fL \
        --retry 5 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 180 \
        -o "$out" \
        "$url"

    if [[ ! -s "$out" ]]; then
        echo "ERROR: Pexels download is empty." >&2
        return 1
    fi

    if ! ffprobe \
        -v error \
        -select_streams v:0 \
        -show_entries stream=codec_name \
        -of csv=p=0 \
        "$out" \
        >/dev/null
    then
        echo "ERROR: Invalid Pexels video." >&2
        return 1
    fi

    printf '%s\n' "$out"
}

make_scene_video() {

    local source="$1"
    local scene_duration="$2"
    local output="$3"

    local vf

    echo "--------------------------------------"
    echo "[VIDEO]"
    echo "Source  : $source"
    echo "Duration: ${scene_duration}s"
    echo "Output  : $output"
    echo "--------------------------------------"

    if [[ "$ANIMATION_ENABLED" == "true" ]]; then

        vf="scale=1280:2280:force_original_aspect_ratio=increase,crop=1280:2280,zoompan=z='min(max(zoom,pzoom)+0.0008,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p"

    else

        vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p"

    fi

    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -stream_loop -1 \
        -i "$source" \
        -t "$scene_duration" \
        -vf "$vf" \
        -an \
        -c:v libx264 \
        -preset veryfast \
        -crf 20 \
        -pix_fmt yuv420p \
        -r 30 \
        -movflags +faststart \
        "$output"

    if [[ ! -s "$output" ]]; then
        echo "ERROR: Scene video was not created." >&2
        return 1
    fi
}

seconds_to_ass() {

    awk \
        -v x="$1" \
        'BEGIN {
            total = int(x * 100 + 0.5)

            h = int(total / 360000)
            m = int((total % 360000) / 6000)
            s = int((total % 6000) / 100)
            c = total % 100

            printf "%d:%02d:%02d.%02d", h, m, s, c
        }'
}

ass_escape() {

    local text="$1"

    text="${text//\\/\\\\}"
    text="${text//\{/\\\{}"
    text="${text//\}/\\\}}"
    text="${text//$/\\$}"

    printf '%s' "$text"
}

create_ass() {

    local output="$RUN_DIR/subtitles/subtitles.ass"

    cat > "$output" <<'ASS'
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding

Style: EN,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,70,70,900,1

Style: AR,DejaVu Sans,52,&H0000FFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,280,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
ASS

    local start=0

    for ((i=1; i<=SCENE_COUNT; i++)); do

        local en
        local ar
        local d
        local end

        en="$(
            jq -r \
                ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" \
                "$JOB_JSON"
        )"

        ar="$(
            jq -r \
                ".scenes[$((i-1))].text_ar // empty" \
                "$JOB_JSON"
        )"

        if [[ -z "$en" || -z "$ar" ]]; then
            echo "ERROR: Scene $i is missing subtitle text." >&2
            return 1
        fi

        d="$(
            duration "$RUN_DIR/audio/scene_${i}.wav"
        )"

        end="$(
            awk \
                -v s="$start" \
                -v d="$d" \
                'BEGIN {
                    printf "%.3f", s+d
                }'
        )"

        printf \
            'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' \
            "$(seconds_to_ass "$start")" \
            "$(seconds_to_ass "$end")" \
            "$(ass_escape "$en")" \
            >> "$output"

        printf \
            'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' \
            "$(seconds_to_ass "$start")" \
            "$(seconds_to_ass "$end")" \
            "$(ass_escape "$ar")" \
            >> "$output"

        start="$end"

    done

    printf '%s\n' "$output"
}

find_music() {

    if [[ -n "${MUSIC_FILE:-}" ]] &&
       [[ -f "$MUSIC_FILE" ]]; then

        printf '%s\n' "$MUSIC_FILE"
        return 0
    fi

    local dir="${MUSIC_DIR:-$RUN_DIR/music}"
    local file

    if [[ ! -d "$dir" ]]; then
        return 1
    fi

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

add_music() {

    local voice="$1"
    local music="$2"
    local output="$3"
    local volume="$4"

    local d

    d="$(
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
        "[0:a]volume=${volume},atrim=0:${d},asetpts=N/SR/TB[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]" \
        -map "[mix]" \
        -ar 48000 \
        -ac 2 \
        -c:a pcm_s16le \
        "$output"

    if [[ ! -s "$output" ]]; then
        echo "ERROR: Music mix failed." >&2
        return 1
    fi
}

concat_videos() {

    local list="$RUN_DIR/video/concat.txt"
    local out="$RUN_DIR/video/visuals.mp4"

    : > "$list"

    for ((i=1; i<=SCENE_COUNT; i++)); do

        printf \
            "file '%s'\n" \
            "$RUN_DIR/video/scene_${i}.mp4" \
            >> "$list"

    done

    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -f concat \
        -safe 0 \
        -i "$list" \
        -c copy \
        -movflags +faststart \
        "$out"

    if [[ ! -s "$out" ]]; then
        echo "ERROR: Video concatenation failed." >&2
        return 1
    fi

    printf '%s\n' "$out"
}

make_final() {

    local visuals="$1"
    local audio="$2"
    local ass="$3"
    local out="$4"

    local escaped_ass

    escaped_ass="$(
        printf '%s' "$ass" |
        sed \
            's/\\/\\\\/g;
             s/:/\\:/g'
    )"

    ffmpeg \
        -hide_banner \
        -loglevel error \
        -y \
        -i "$visuals" \
        -i "$audio" \
        -vf "subtitles=${escaped_ass}" \
        -map 0:v:0 \
        -map 1:a:0 \
        -c:v libx264 \
        -preset veryfast \
        -crf 20 \
        -pix_fmt yuv420p \
        -r 30 \
        -c:a aac \
        -b:a 192k \
        -ar 48000 \
        -ac 2 \
        -shortest \
        -movflags +faststart \
        "$out"

    if [[ ! -s "$out" ]]; then
        echo "ERROR: Final video was not created." >&2
        return 1
    fi
}

validate_final() {

    local f="$1"

    local d
    local w
    local h
    local vcodec
    local acodec

    d="$(duration "$f")"

    w="$(
        ffprobe \
            -v error \
            -select_streams v:0 \
            -show_entries stream=width \
            -of csv=p=0 \
            "$f" |
        head -n1
    )"

    h="$(
        ffprobe \
            -v error \
            -select_streams v:0 \
            -show_entries stream=height \
            -of csv=p=0 \
            "$f" |
        head -n1
    )"

    vcodec="$(
        ffprobe \
            -v error \
            -select_streams v:0 \
            -show_entries stream=codec_name \
            -of csv=p=0 \
            "$f" |
        head -n1
    )"

    acodec="$(
        ffprobe \
            -v error \
            -select_streams a:0 \
            -show_entries stream=codec_name \
            -of csv=p=0 \
            "$f" |
        head -n1
    )"

    if ! awk \
        -v d="$d" \
        'BEGIN {
            exit !(d >= 30 && d <= 60)
        }'
    then
        echo "ERROR: Final duration ${d}s is outside 30-60 seconds." >&2
        return 1
    fi

    if [[ "$w" != "1080" || "$h" != "1920" ]]; then
        echo "ERROR: Final resolution is ${w}x${h}, expected 1080x1920." >&2
        return 1
    fi

    if [[ "$vcodec" != "h264" ]]; then
        echo "ERROR: Final video codec is $vcodec, expected h264." >&2
        return 1
    fi

    if [[ "$acodec" != "aac" ]]; then
        echo "ERROR: Final audio codec is $acodec, expected aac." >&2
        return 1
    fi

    echo "Final validation passed: ${d}s, ${w}x${h}, H.264/AAC."
}

echo
echo "======================================"
echo "YOUTUBE SHORTS PRODUCTION"
echo "======================================"
echo "Run directory : $RUN_DIR"
echo "Voice         : $VOICE"
echo "Speed         : $SPEED"
echo "Language      : $LANG_CODE"
echo "Music         : $MUSIC_ENABLED"
echo "Music volume  : $MUSIC_VOLUME"
echo "Animation     : $ANIMATION_ENABLED"
echo "Ads           : DISABLED"
echo "Scenes        : $SCENE_COUNT"
echo "======================================"
echo

for ((i=1; i<=SCENE_COUNT; i++)); do

    TEXT="$(
        jq -r \
            ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" \
            "$JOB_JSON"
    )"

    QUERY="$(
        jq -r \
            ".scenes[$((i-1))].pexels_query // .scenes[$((i-1))].query // empty" \
            "$JOB_JSON"
    )"

    if [[ -z "$TEXT" ]]; then
        echo "ERROR: Scene $i has no narration." >&2
        exit 1
    fi

    if [[ -z "$QUERY" ]]; then
        echo "ERROR: Scene $i has no Pexels query." >&2
        exit 1
    fi

    echo
    echo "======================================"
    echo "SCENE $i / $SCENE_COUNT"
    echo "======================================"

    echo "[SCENE $i/$SCENE_COUNT] Generating voice..."

    generate_voice \
        "$TEXT" \
        "$RUN_DIR/audio/scene_${i}.wav"

    DURATION="$(
        duration "$RUN_DIR/audio/scene_${i}.wav"
    )"

    echo "Audio duration: ${DURATION}s"

    echo "[SCENE $i/$SCENE_COUNT] Downloading Pexels video..."

    SOURCE="$(
        pexels_video \
            "$QUERY" \
            "$i"
    )"

    echo "[SCENE $i/$SCENE_COUNT] Rendering visual..."

    make_scene_video \
        "$SOURCE" \
        "$DURATION" \
        "$RUN_DIR/video/scene_${i}.mp4"

done

TOTAL_DURATION="0"

for ((i=1; i<=SCENE_COUNT; i++)); do

    SCENE_DURATION="$(
        duration "$RUN_DIR/audio/scene_${i}.wav"
    )"

    TOTAL_DURATION="$(
        awk \
            -v t="$TOTAL_DURATION" \
            -v d="$SCENE_DURATION" \
            'BEGIN {
                printf "%.3f", t+d
            }'
    )"

done

if ! awk \
    -v d="$TOTAL_DURATION" \
    'BEGIN {
        exit !(d >= 30 && d <= 60)
    }'
then
    echo "ERROR: Total narration duration ${TOTAL_DURATION}s is outside 30-60 seconds." >&2
    echo "Adjust Gemini script length." >&2
    exit 1
fi

AUDIO_FINAL="$RUN_DIR/audio/voice_final.wav"

if [[ "$MUSIC_ENABLED" == "true" ]]; then

    if MUSIC="$(find_music)"; then

        echo "Adding background music: $MUSIC"

        if (( SCENE_COUNT == 1 )); then

            add_music \
                "$RUN_DIR/audio/scene_1.wav" \
                "$MUSIC" \
                "$AUDIO_FINAL" \
                "$MUSIC_VOLUME"

        else

            : > "$RUN_DIR/audio/voice_concat.txt"

            for ((i=1; i<=SCENE_COUNT; i++)); do

                printf \
                    "file '%s'\n" \
                    "$RUN_DIR/audio/scene_${i}.wav" \
                    >> "$RUN_DIR/audio/voice_concat.txt"

            done

            ffmpeg \
                -hide_banner \
                -loglevel error \
                -y \
                -f concat \
                -safe 0 \
                -i "$RUN_DIR/audio/voice_concat.txt" \
                -c:a pcm_s16le \
                "$RUN_DIR/audio/voice_concat.wav"

            add_music \
                "$RUN_DIR/audio/voice_concat.wav" \
                "$MUSIC" \
                "$AUDIO_FINAL" \
                "$MUSIC_VOLUME"

        fi

    else

        echo "No music file found; continuing without music."

        if (( SCENE_COUNT == 1 )); then

            cp \
                "$RUN_DIR/audio/scene_1.wav" \
                "$AUDIO_FINAL"

        else

            : > "$RUN_DIR/audio/voice_concat.txt"

            for ((i=1; i<=SCENE_COUNT; i++)); do

                printf \
                    "file '%s'\n" \
                    "$RUN_DIR/audio/scene_${i}.wav" \
                    >> "$RUN_DIR/audio/voice_concat.txt"

            done

            ffmpeg \
                -hide_ban
