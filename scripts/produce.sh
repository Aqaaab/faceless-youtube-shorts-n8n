#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${1:-${RUN_DIR:-}}"
if [[ -z "$RUN_DIR" ]]; then
  echo "Usage: $0 <RUN_DIR>" >&2
  exit 2
fi

JOB_JSON="$RUN_DIR/job.json"
[[ -f "$JOB_JSON" ]] || { echo "ERROR: Missing $JOB_JSON" >&2; exit 1; }

for bin in ffmpeg ffprobe jq curl; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "ERROR: $bin is required" >&2
    exit 1
  }
done

PEXELS_API_KEY="${PEXELS_API_KEY:-}"
[[ -n "$PEXELS_API_KEY" ]] || {
  echo "ERROR: PEXELS_API_KEY is not set" >&2
  exit 1
}

mkdir -p "$RUN_DIR"/{scenes,audio,video,subtitles,downloads,music}

VOICE="$(jq -r '.voice // "af_bella"' "$JOB_JSON")"
SPEED="$(jq -r '.speed // 1.0' "$JOB_JSON")"
LANG="$(jq -r '.lang // "en-us"' "$JOB_JSON")"
MUSIC_ENABLED="$(jq -r 'if .music == false then "false" else "true" end' "$JOB_JSON")"
MUSIC_VOLUME="$(jq -r '.music_volume // 0.10' "$JOB_JSON")"
ANIMATION_ENABLED="$(jq -r 'if .animation == false then "false" else "true" end' "$JOB_JSON")"
ADS_ENABLED="$(jq -r 'if .ads == true then "true" else "false" end' "$JOB_JSON")"

[[ "$ADS_ENABLED" == "false" ]] || {
  echo "ERROR: Ads are disabled." >&2
  exit 1
}

SCENE_COUNT="$(jq '.scenes | length' "$JOB_JSON")"

[[ "$SCENE_COUNT" =~ ^[0-9]+$ ]] &&
(( SCENE_COUNT >= 1 )) || {
  echo "ERROR: No scenes found in job.json" >&2
  exit 1
}

KOKORO_BIN="${KOKORO_BIN:-}"

if [[ -z "$KOKORO_BIN" ]]; then
  for candidate in kokoro-tts kokoro_tts; do
    if command -v "$candidate" >/dev/null 2>&1; then
      KOKORO_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

[[ -n "$KOKORO_BIN" ]] || {
  echo "ERROR: Kokoro TTS CLI not found." >&2
  exit 1
}

duration() {
  ffprobe -v error \
    -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$1" |
    awk '{printf "%.3f", $1}'
}

generate_voice() {

  local text="$1"
  local output="$2"
  local tmp="${output}.tmp.wav"
  local txt="${output}.txt"

  rm -f "$tmp" "$output" "$txt"

  printf '%s\n' "$text" > "$txt"

  if "$KOKORO_BIN" \
      "$txt" "$tmp" \
      --voice "$VOICE" \
      --speed "$SPEED" \
      --lang "$LANG" \
      >/dev/null 2>&1
  then
    :
  elif "$KOKORO_BIN" \
      --text "$text" \
      --voice "$VOICE" \
      --speed "$SPEED" \
      --language "$LANG" \
      --output-file "$tmp" \
      >/dev/null 2>&1
  then
    :
  else
    rm -f "$tmp" "$txt"
    return 1
  fi

  [[ -s "$tmp" ]] || return 1

  ffmpeg -hide_banner -loglevel error -y \
    -i "$tmp" \
    -ar 48000 \
    -ac 2 \
    -c:a pcm_s16le \
    "$output"

  rm -f "$tmp" "$txt"
}

pexels_video() {

  local query="$1"
  local index="$2"

  local json="$RUN_DIR/downloads/pexels_${index}.json"
  local output="$RUN_DIR/downloads/scene_${index}.mp4"

  curl -fsSL \
    --retry 3 \
    --retry-delay 1 \
    -H "Authorization: $PEXELS_API_KEY" \
    --get \
    "https://api.pexels.com/videos/search" \
    --data-urlencode "query=$query" \
    --data-urlencode "orientation=portrait" \
    --data-urlencode "size=medium" \
    --data-urlencode "per_page=10" \
    > "$json"

  local url

  url="$(
    jq -r '
      [
        .videos[]?.video_files[]?
        | select(.file_type == "video/mp4")
        | select(.link != null)
        | select(.width != null and .height != null)
      ]
      | sort_by(.width * .height)
      | reverse
      | .[0].link // empty
    ' "$json"
  )"

  [[ -n "$url" ]] || return 1

  curl -fL \
    --retry 3 \
    --retry-delay 1 \
    -o "$output" \
    "$url"

  [[ -s "$output" ]] || return 1

  printf '%s' "$output"
}

make_scene_video() {

  local source="$1"
  local duration_value="$2"
  local output="$3"

  local filter

  if [[ "$ANIMATION_ENABLED" == "true" ]]; then

    filter="
      scale=1200:2134:force_original_aspect_ratio=increase,
      crop=1200:2134,
      zoompan=
        z='min(zoom+0.0008,1.08)':
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
      scale=1080:1920:force_original_aspect_ratio=increase,
      crop=1080:1920,
      setsar=1,
      fps=30,
      format=yuv420p
    "

  fi

  ffmpeg -hide_banner -loglevel error -y \
    -stream_loop -1 \
    -i "$source" \
    -t "$duration_value" \
    -vf "$filter" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -crf 20 \
    -movflags +faststart \
    "$output"
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

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: EN,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,70,70,900,1
Style: AR,Arial,52,&H0000FFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,280,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
EOF

  local start_cs=0

  for ((i=1; i<=SCENE_COUNT; i++)); do

    local text
    local arabic
    local d
    local end_cs
    local start
    local end

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
      echo "ERROR: Scene $i missing English text" >&2
      exit 1
    }

    [[ -n "$arabic" ]] || {
      echo "ERROR: Scene $i missing Arabic text" >&2
      exit 1
    }

    d="$(duration "$RUN_DIR/audio/scene_${i}.wav")"

    end_cs="$(
      awk \
      -v s="$start_cs" \
      -v d="$d" \
      'BEGIN {printf "%d",(s+d*100)+0.5}'
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

    local en
    local ar

    en="$(ass_escape "$text")"
    ar="$(ass_escape "$arabic")"

    printf \
      'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' \
      "$start" "$end" "$en" \
      >> "$output"

    printf \
      'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' \
      "$start" "$end" "$ar" \
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

  local dir="${MUSIC_DIR:-/scripts/music}"

  if [[ -d "$dir" ]]; then

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

  fi

  return 1
}

add_music() {

  local voice="$1"
  local music="$2"
  local output="$3"
  local volume="$4"

  local voice_duration

  voice_duration="$(duration "$voice")"

  ffmpeg -hide_banner -loglevel error -y \
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
}

echo "[produce] Starting production"
echo "[produce] Voice: $VOICE"
echo "[produce] Music: $MUSIC_ENABLED"
echo "[produce] Animation: $ANIMATION_ENABLED"
echo "[produce] Ads: DISABLED"

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

  echo "[produce] Scene $i/$SCENE_COUNT"
  echo "[produce] Query: $QUERY"

  generate_voice \
    "$TEXT" \
    "$RUN_DIR/audio/scene_${i}.wav" || {
      echo "ERROR: Kokoro failed on scene $i" >&2
      exit 1
    }

  DURATION="$(
    duration "$RUN_DIR/audio/scene_${i}.wav"
  )"

  SOURCE="$(
    pexels_video "$QUERY" "$i"
  )" || {
    echo "ERROR: Pexels failed for scene $i" >&2
    exit 1
  }

  make_scene_video \
    "$SOURCE" \
    "$DURATION" \
    "$RUN_DIR/video/scene_${i}.mp4"

done

ASS_FILE="$(create_ass)"

VIDEO_LIST="$RUN_DIR/video_list.txt"
: > "$VIDEO_LIST"

for ((i=1; i<=SCENE_COUNT; i++)); do

  printf \
    "file '%s'\n" \
    "$(realpath "$RUN_DIR/video/scene_${i}.mp4")" \
    >> "$VIDEO_LIST"

done

ffmpeg -hide_banner -loglevel error -y \
  -f concat \
  -safe 0 \
  -i "$VIDEO_LIST" \
  -c:v libx264 \
  -preset veryfast \
  -crf 20 \
  -pix_fmt yuv420p \
  -r 30 \
  -an \
  "$RUN_DIR/video_concat.mp4"

AUDIO_LIST="$RUN_DIR/audio_list.txt"
: > "$AUDIO_LIST"

for ((i=1; i<=SCENE_COUNT; i++)); do

  printf \
    "file '%s'\n" \
    "$(realpath "$RUN_DIR/audio/scene_${i}.wav")" \
    >> "$AUDIO_LIST"

done

ffmpeg -hide_banner -loglevel error -y \
  -f concat \
  -safe 0 \
  -i "$AUDIO_LIST" \
  -ar 48000 \
  -ac 2 \
  -c:a pcm_s16le \
  "$RUN_DIR/audio/voice_concat.wav"

FINAL_AUDIO="$RUN_DIR/audio/voice_concat.wav"

if [[ "$MUSIC_ENABLED" == "true" ]]; then

  MUSIC="$(find_music || true)"

  if [[ -n "$MUSIC" ]]; then

    echo "[produce] Adding background music"

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

cp "$FINAL_AUDIO" "$RUN_DIR/all_voice.wav"

ASS_FILTER="$(
  printf '%s' "$ASS_FILE" |
  sed 's/\\/\\\\/g; s/:/\\:/g; s/,/\\,/g'
)"

ffmpeg -hide_banner -loglevel error -y \
  -i "$RUN_DIR/video_concat.mp4" \
  -i "$FINAL_AUDIO" \
  -vf "ass=${ASS_FILTER}" \
  -map 0:v:0 \
  -map 1:a:0 \
  -c:v libx264 \
  -preset veryfast \
  -crf 20 \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -ar 48000 \
  -ac 2 \
  -shortest \
  -movflags +faststart \
  "$RUN_DIR/final_video.mp4"

cp "$RUN_DIR/final_video.mp4" "$RUN_DIR/video.mp4"

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

AUDIO_CODEC="$(
  ffprobe \
    -v error \
    -select_streams a:0 \
    -show_entries stream=codec_name \
    -of csv=p=0 \
    "$RUN_DIR/video.mp4"
)"

echo "[produce] Resolution: $SIZE"
echo "[produce] Duration: ${DURATION}s"
echo "[produce] Audio: $AUDIO_CODEC"

[[ "$SIZE" == "1080x1920" ]] || {
  echo "ERROR: Video must be 1080x1920" >&2
  exit 1
}

[[ "$AUDIO_CODEC" == "aac" ]] || {
  echo "ERROR: Audio must be AAC" >&2
  exit 1
}

awk -v d="$DURATION" \
  'BEGIN {exit !(d >= 30 && d <= 60)}' || {
  echo "ERROR: Duration must be 30-60 seconds" >&2
  exit 1
}

echo "======================================"
echo "PRODUCTION COMPLETE"
echo "======================================"
echo "Video: $RUN_DIR/video.mp4"
echo "Voice: $RUN_DIR/all_voice.wav"
echo "Subs:  $ASS_FILE"
echo "Ads:   DISABLED"
echo "Voice: Kokoro / af_bella"
echo "======================================"
