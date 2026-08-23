#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${1:-${RUN_DIR:-}}"

if [[ -z "$RUN_DIR" ]]; then
  echo "ERROR: Usage: $0 <RUN_DIR>" >&2
  exit 2
fi

JOB_JSON="$RUN_DIR/job.json"

[[ -f "$JOB_JSON" ]] || {
  echo "ERROR: Missing $JOB_JSON" >&2
  exit 1
}

export PATH="${HOME}/.local/bin:${PATH}"

for bin in ffmpeg ffprobe jq curl awk sed realpath; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "ERROR: Required command not found: $bin" >&2
    exit 1
  }
done

PEXELS_API_KEY="${PEXELS_API_KEY:-}"

[[ -n "$PEXELS_API_KEY" ]] || {
  echo "ERROR: PEXELS_API_KEY is not set." >&2
  exit 1
}

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
  echo "ERROR: Ads are currently disabled by design." >&2
  exit 1
fi

if ! awk -v speed="$SPEED" \
  'BEGIN {exit !(speed >= 0.5 && speed <= 2.0)}'
then
  echo "ERROR: SPEED must be between 0.5 and 2.0." >&2
  exit 1
fi

if ! awk -v volume="$MUSIC_VOLUME" \
  'BEGIN {exit !(volume >= 0 && volume <= 1)}'
then
  echo "ERROR: MUSIC_VOLUME must be between 0 and 1." >&2
  exit 1
fi

SCENE_COUNT="$(
  jq '.scenes | length' "$JOB_JSON"
)"

if ! [[ "$SCENE_COUNT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: Invalid scene count." >&2
  exit 1
fi

if (( SCENE_COUNT < 1 )); then
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
  echo "ERROR: Kokoro TTS CLI was not found." >&2
  exit 1
fi

[[ -x "$KOKORO_BIN" ]] || {
  echo "ERROR: Kokoro binary is not executable: $KOKORO_BIN" >&2
  exit 1
}

KOKORO_PATH="${KOKORO_PATH:-}"

if [[ -z "$KOKORO_PATH" ]]; then
  if [[ -f "$PWD/kokoro-models/kokoro-v1.0.onnx" ]]; then
    KOKORO_PATH="$PWD/kokoro-models"
  elif [[ -f "$PWD/kokoro-v1.0.onnx" ]]; then
    KOKORO_PATH="$PWD"
  fi
fi

if [[ -n "$KOKORO_PATH" ]]; then

  export KOKORO_PATH

  MODEL_FILE="$KOKORO_PATH/kokoro-v1.0.onnx"
  VOICES_FILE="$KOKORO_PATH/voices-v1.0.bin"

  [[ -s "$MODEL_FILE" ]] || {
    echo "ERROR: Missing Kokoro model:" >&2
    echo "$MODEL_FILE" >&2
    exit 1
  }

  [[ -s "$VOICES_FILE" ]] || {
    echo "ERROR: Missing Kokoro voices file:" >&2
    echo "$VOICES_FILE" >&2
    exit 1
  }

else

  echo "ERROR: KOKORO_PATH was not found." >&2
  echo "Expected kokoro-v1.0.onnx and voices-v1.0.bin." >&2
  exit 1

fi

duration() {

  local file="$1"

  [[ -s "$file" ]] || {
    echo "ERROR: Cannot measure missing/empty file: $file" >&2
    return 1
  }

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

  local error_log="${output_file}.kokoro.log"
  local tmp_output="${output_file}.tmp.wav"

  rm -f \
    "$output_file" \
    "$tmp_output" \
    "$error_log"

  echo "[produce] Kokoro input: $text_file"
  echo "[produce] Kokoro output: $output_file"
  echo "[produce] Kokoro voice: $VOICE"
  echo "[produce] Kokoro speed: $SPEED"
  echo "[produce] Kokoro language: $LANG_CODE"
  echo "[produce] Kokoro path: $KOKORO_PATH"

  if "$KOKORO_BIN" \
      "$text_file" \
      "$tmp_output" \
      --voice "$VOICE" \
      --speed "$SPEED" \
      --lang "$LANG_CODE" \
      --debug \
      2>&1 | tee "$error_log"
  then
    :
  else

    echo "======================================" >&2
    echo "KOKORO FAILED" >&2
    echo "======================================" >&2
    cat "$error_log" >&2 || true
    echo "======================================" >&2

    rm -f "$tmp_output"

    return 1

  fi

  [[ -s "$tmp_output" ]] || {
    echo "ERROR: Kokoro produced no audio." >&2
    cat "$error_log" >&2 || true
    rm -f "$tmp_output"
    return 1
  }

  ffmpeg \
    -hide_banner \
    -loglevel error \
    -y \
    -i "$tmp_output" \
    -ar 48000 \
    -ac 2 \
    -c:a pcm_s16le \
    "$output_file"

  [[ -s "$output_file" ]] || {
    echo "ERROR: Failed to normalize Kokoro output." >&2
    rm -f "$tmp_output"
    return 1
  }

  rm -f "$tmp_output"

  duration "$output_file" >/dev/null || {
    echo "ERROR: Generated audio has invalid duration." >&2
    return 1
  }

  echo "[produce] Kokoro audio generated successfully."

  return 0
}

generate_voice() {

  local text="$1"
  local output="$2"

  local txt="${output}.txt"

  rm -f \
    "$output" \
    "$txt"

  if [[ -z "${text//[[:space:]]/}" ]]; then
    echo "ERROR: Empty narration text." >&2
    return 1
  fi

  printf '%s\n' "$text" > "$txt"

  run_kokoro \
    "$txt" \
    "$output"

  local result=$?

  rm -f "$txt"

  return "$result"
}

pexels_video() {

  local query="$1"
  local index="$2"

  local json="$RUN_DIR/downloads/pexels_${index}.json"
  local output="$RUN_DIR/downloads/scene_${index}.mp4"

  rm -f "$json" "$output"

  echo "[produce] Searching Pexels: $query"

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
    > "$json"

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
      | sort_by(.pixels)
      | reverse
      | .[0].link // empty
    ' "$json"
  )"

  if [[ -z "$url" ]]; then
    echo "ERROR: Pexels returned no usable video for: $query" >&2
    echo "Pexels response:" >&2
    jq '.' "$json" >&2 || cat "$json" >&2
    return 1
  fi

  echo "[produce] Downloading Pexels video..."

  curl \
    -fL \
    --retry 5 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 180 \
    -o "$output" \
    "$url"

  [[ -s "$output" ]] || {
    echo "ERROR: Pexels video download is empty." >&2
    return 1
  }

  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries stream=codec_name \
    -of csv=p=0 \
    "$output" >/dev/null || {
      echo "ERROR: Downloaded Pexels file is not a valid video." >&2
      return 1
    }

  printf '%s' "$output"
}

make_scene_video() {

  local source="$1"
  local duration_value="$2"
  local output="$3"

  local filter=""

  if [[ "$ANIMATION_ENABLED" == "true" ]]; then

    filter="
      scale=1080:1920:
        force_original_aspect_ratio=increase,
      crop=1080:1920,
      zoompan=
        z='min(zoom+0.001,1.10)':
        x='iw/2-(iw/zoom/2)':
        y='ih/2-(ih/zoom/2)':
        d=1:
        s=1080x1920:
        fps=30,
      setsar=1,
      format=yuv420p
    "

  else

    filter="
      scale=1080:1920:
        force_original_aspect_ratio=increase,
      crop=1080:1920,
      fps=30,
      setsar=1,
      format=yuv420p
    "

  fi

  echo "[produce] Creating scene video: $output"

  ffmpeg \
    -hide_banner \
    -loglevel error \
    -y \
    -stream_loop -1 \
    -i "$source" \
    -t "$duration_value" \
    -vf "$filter" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -crf 20 \
    -pix_fmt yuv420p \
    -r 30 \
    -movflags +faststart \
    "$output"

  [[ -s "$output" ]] || {
    echo "ERROR: Scene video was not created." >&2
    return 1
  }
}

ass_escape() {

  local text="$1"

  text="${text//\\/\\\\}"
  text="${text//\{/\\{}"
  text="${text//\}/\\}}"

  printf '%s' "$text"
}

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

  local start_cs=0

  for ((i=1; i<=SCENE_COUNT; i++)); do

    local text=""
    local arabic=""
    local d=""
    local end_cs=""
    local start=""
    local end=""
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

    [[ -n "$text" ]] || {
      echo "ERROR: Scene $i missing English text." >&2
      exit 1
    }

    [[ -n "$arabic" ]] || {
      echo "ERROR: Scene $i missing Arabic text." >&2
      exit 1
    }

    d="$(
      duration "$RUN_DIR/audio/scene_${i}.wav"
    )"

    end_cs="$(
      awk \
        -v s="$start_cs" \
        -v d="$d" \
        'BEGIN {
          printf "%d",(s+d*100)+0.5
        }'
    )"

    start="$(
      awk \
        -v x="$start_cs" \
        'BEGIN {
          h=int(x/360000);
          m=int((x%360000)/6000);
          s=int((x%6000)/100);
          c=x%100;
          printf "%d:%02d:%02d.%02d",h,m,s,c
        }'
    )"

    end="$(
      awk \
        -v x="$end_cs" \
        'BEGIN {
          h=int(x/360000);
          m=int((x%360000)/6000);
          s=int((x%6000)/100);
          c=x%100;
          printf "%d:%02d:%02d.%02d",h,m,s,c
        }'
    )"

    en="$(ass_escape "$text")"
    ar="$(ass_escape "$arabic")"

    printf \
      'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' \
      "$start" \
      "$end" \
      "$en" \
      >> "$output"

    printf \
      'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' \
      "$start" \
      "$end" \
      "$ar" \
      >> "$output"

    start_cs="$end_cs"

  done

  printf '%s\n' "$output"
}

find_music() {

  if [[ -n "${MUSIC_FILE:-}" ]] &&
     [[ -f "$MUSIC_FILE" ]]; then

    printf '%s' "$MUSIC_FILE"
    return 0
  fi

  local dir="${MUSIC_DIR:-$RUN_DIR/music}"

  [[ -d "$dir" ]] || return 1

  local file=""

  for file in \
    "$dir"/*.mp3 \
    "$dir"/*.wav \
    "$dir"/*.m4a \
    "$dir"/*.aac
  do

    if [[ -f "$file" ]]; then
      printf '%s' "$file"
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

  local voice_duration=""

  voice_duration="$(duration "$voice")"

  ffmpeg \
    -hide_banner \
    -loglevel error \
    -y \
    -stream_loop -1 \
    -i "$music" \
    -i "$voice" \
    -filter_complex \
    "[0:a]volume=${volume},atrim=0:${voice_duration},asetpts=N/SR/TB[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]" \
    -map "[a]" \
    -ar 48000 \
    -ac 2 \
    -c:a pcm_s16le \
    "$output"

  [[ -s "$output" ]] || {
    echo "ERROR: Music mix failed." >&2
    return 1
  }
}

echo "======================================"
echo "[produce] Starting production"
echo "======================================"
echo "[produce] Voice: $VOICE"
echo "[produce] Speed: $SPEED"
echo "[produce] Language: $LANG_CODE"
echo "[produce] Music: $MUSIC_ENABLED"
echo "[produce] Animation: $ANIMATION_ENABLED"
echo "[produce] Ads: DISABLED"
echo "[produce] Scenes: $SCENE_COUNT"
echo "[produce] Kokoro: $KOKORO_BIN"
echo "[produce] Kokoro path: $KOKORO_PATH"
echo "======================================"

for ((i=1; i<=SCENE_COUNT; i++)); do

  TEXT="$(
    jq -r \
      ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" \
      "$JOB_JSON"
  )"

  QUERY="$(
    jq -r \
      ".scenes[$((i-1))].pexels_query // .scenes[$((i-1))].query // \"abstract background\"" \
      "$JOB_JSON"
  )"

  [[ -n "$TEXT" ]] || {
    echo "ERROR: Scene $i has no narration." >&2
    exit 1
  }

  [[ -n "$QUERY" ]] || {
    echo "ERROR: Scene $i has no Pexels query." >&2
    exit 1
  }

  echo "======================================"
  echo "[produce] Scene $i/$SCENE_COUNT"
  echo "[produce] Query: $QUERY"
  echo "======================================"

  if ! generate_voice \
    "$TEXT" \
    "$RUN_DIR/audio/scene_${i}.wav"
  then

    echo "======================================" >&2
    echo "ERROR: Kokoro failed on scene $i" >&2
    echo "======================================" >&2

    if [[ -f "$RUN_DIR/audio/scene_${i}.wav.kokoro.log" ]]; then
      cat \
        "$RUN_DIR/audio/scene_${i}.wav.kokoro.log" \
        >&2
    fi

    exit 1
  fi

  DURATION="$(
    duration "$RUN_DIR/audio/scene_${i}.wav"
  )"

  echo "[produce] Scene audio duration: ${DURATION}s"

  SOURCE="$(
    pexels_video "$QUERY" "$i"
  )" || {
    echo "ERROR: Pexels failed for scene $i." >&2
    exit 1
  }

  make_scene_video \
    "$SOURCE" \
    "$DURATION" \
    "$RUN_DIR/video/scene_${i}.mp4"

done

ASS_FILE="$(create_ass)"

[[ -s "$ASS_FILE" ]] || {
  echo "ERROR: ASS subtitle file was not created." >&2
  exit 1
}

VIDEO_LIST="$RUN_DIR/video_list.txt"

: > "$VIDEO_LIST"

for ((i=1; i<=SCENE_COUNT; i++)); do

  VIDEO_FILE="$(
    realpath "$RUN_DIR/video/scene_${i}.mp4"
  )"

  [[ -s "$VIDEO_FILE" ]] || {
    echo "ERROR: Missing scene video: $VIDEO_FILE" >&2
    exit 1
  }

  printf "file '%s'\n" "$VIDEO_FILE" >> "$VIDEO_LIST"

done

echo "[produce] Concatenating video..."

ffmpeg \
  -hide_banner \
  -loglevel error \
  -y \
  -f concat \
  -safe 0 \
  -i "$VIDEO_LIST" \
  -c:v libx264 \
  -preset veryfast \
  -crf 20 \
  -pix_fmt yuv420p \
  -r 30 \
  -an \
  -movflags +faststart \
  "$RUN_DIR/video_concat.mp4"

[[ -s "$RUN_DIR/video_concat.mp4" ]] || {
  echo "ERROR: Video concatenation failed." >&2
  exit 1
}

AUDIO_LIST="$RUN_DIR/audio_list.txt"

: > "$AUDIO_LIST"

for ((i=1; i<=SCENE_COUNT; i++)); do

  AUDIO_FILE="$(
    realpath "$RUN_DIR/audio/scene_${i}.wav"
  )"

  [[ -s "$AUDIO_FILE" ]] || {
    echo "ERROR: Missing scene audio: $AUDIO_FILE" >&2
    exit 1
  }

  printf "file '%s'\n" "$AUDIO_FILE" >> "$AUDIO_LIST"

done

echo "[produce] Concatenating audio..."

ffmpeg \
  -hide_banner \
  -loglevel error \
  -y \
  -f concat \
  -safe 0 \
  -i "$AUDIO_LIST" \
  -ar 48000 \
  -ac 2 \
  -c:a pcm_s16le \
  "$RUN_DIR/audio/voice_concat.wav"

[[ -s "$RUN_DIR/audio/voice_concat.wav" ]] || {
  echo "ERROR: Audio concatenation failed." >&2
  exit 1
}

FINAL_AUDIO="$RUN_DIR/audio/voice_concat.wav"

if [[ "$MUSIC_ENABLED" == "true" ]]; then

  MUSIC="$(find_music || true)"

  if [[ -n "$MUSIC" ]]; then

    echo "[produce] Adding background music:"
    echo "$MUSIC"

    add_music \
      "$FINAL_AUDIO" \
      "$MUSIC" \
      "$RUN_DIR/audio/final_mix.wav" \
      "$MUSIC_VOLUME"

    FINAL_AUDIO="$RUN_DIR/audio/final_mix.wav"

  else

    echo "[produce] No music file found. Voice only."

  fi

fi

cp \
  "$FINAL_AUDIO" \
  "$RUN_DIR/all_voice.wav"

[[ -s "$RUN_DIR/all_voice.wav" ]] || {
  echo "ERROR: Final voice file was not created." >&2
  exit 1
}

ASS_FILTER="$(
  printf '%s' "$ASS_FILE" |
  sed \
    's/\\/\\\\/g; s/:/\\:/g; s/,/\\,/g'
)"

echo "[produce] Rendering final video..."

ffmpeg \
  -hide_banner \
  -loglevel error \
  -y \
  -i "$RUN_DIR/video_concat.mp4" \
  -i "$FINAL_AUDIO" \
  -vf "ass=${ASS_FILTER}" \
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
  "$RUN_DIR/final_video.mp4"

[[ -s "$RUN_DIR/final_video.mp4" ]] || {
  echo "ERROR: Final video rendering failed." >&2
  exit 1
}

cp \
  "$RUN_DIR/final_video.mp4" \
  "$RUN_DIR/video.mp4"

SIZE="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries stream=width,height \
    -of csv=p=0:s=x \
    "$RUN_DIR/video.mp4"
)"

DURATION="$(
  duration "$RUN_DIR/video.mp4"
)"

VIDEO_CODEC="$(
  ffprobe \
    -v error \
    -select_streams v:0 \
    -show_entries stream=codec_name \
    -of csv=p=0 \
    "$RUN_DIR/video.mp4"
)"

AUDIO_CODEC="$(
  ffprobe \
    -v error \
    -select_streams a:0 \
    -show_entries stream=codec_name \
    -of csv=p=0 \
    "$RUN_DIR/video.mp4"
)"

echo "======================================"
echo "FINAL VIDEO CHECK"
echo "======================================"
echo "Resolution: $SIZE"
echo "Duration: ${DURATION}s"
echo "Video codec: $VIDEO_CODEC"
echo "Audio codec: $AUDIO_CODEC"
echo "======================================"

[[ "$SIZE" == "1080x1920" ]] || {
  echo "ERROR: Video must be 1080x1920." >&2
  exit 1
}

[[ "$VIDEO_CODEC" == "h264" ]] || {
  echo "ERROR: Video must use H.264." >&2
  exit 1
}

[[ "$AUDIO_CODEC" == "aac" ]] || {
  echo "ERROR: Audio must be AAC." >&2
  exit 1
}

awk -v d="$DURATION" \
  'BEGIN {exit !(d >= 30 && d <= 60)}' || {
    echo "ERROR: Duration must be between 30 and 60 seconds." >&2
    exit 1
  }

echo "======================================"
echo "PRODUCTION COMPLETE"
echo "======================================"
echo "Video: $RUN_DIR/video.mp4"
echo "Voice: $RUN_DIR/all_voice.wav"
echo "Subs:  $ASS_FILE"
echo "Ads:   DISABLED"
echo "Voice: Kokoro / $VOICE"
echo "======================================"
