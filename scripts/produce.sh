#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${RUN_DIR:-${1:-/data/job}}"
JOB_FILE="${JOB_FILE:-$RUN_DIR/job.json}"
KOKORO_BIN="${KOKORO_BIN:-$(command -v kokoro-tts 2>/dev/null || true)}"
KOKORO_MODEL="${KOKORO_MODEL:-}"
KOKORO_VOICES="${KOKORO_VOICES:-}"
VOICE="${VOICE:-af_bella}"
LANG_CODE="${LANG_CODE:-en-us}"
SPEED="${SPEED:-1.0}"
MUSIC_ENABLED="${MUSIC_ENABLED:-true}"
MUSIC_VOLUME="${MUSIC_VOLUME:-0.10}"
ANIMATION_ENABLED="${ANIMATION_ENABLED:-true}"

[[ -f "$JOB_FILE" ]] || { echo "ERROR: job.json not found: $JOB_FILE" >&2; exit 1; }
for bin in ffmpeg ffprobe jq curl awk sed; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: required command missing: $bin" >&2; exit 1; }
done
mkdir -p "$RUN_DIR" "$RUN_DIR/audio" "$RUN_DIR/scenes" "$RUN_DIR/video" "$RUN_DIR/subtitles" "$RUN_DIR/downloads" "$RUN_DIR/music"

[[ -n "$KOKORO_BIN" ]] || { echo "ERROR: kokoro-tts CLI was not found." >&2; exit 1; }

if [[ -z "$KOKORO_MODEL" ]]; then
  if [[ -n "${KOKORO_PATH:-}" && -f "$KOKORO_PATH/kokoro-v1.0.onnx" ]]; then
    KOKORO_MODEL="$KOKORO_PATH/kokoro-v1.0.onnx"
  elif [[ -f "$PWD/kokoro-models/kokoro-v1.0.onnx" ]]; then
    KOKORO_MODEL="$PWD/kokoro-models/kokoro-v1.0.onnx"
  fi
fi
if [[ -z "$KOKORO_VOICES" ]]; then
  if [[ -n "${KOKORO_PATH:-}" && -f "$KOKORO_PATH/voices-v1.0.bin" ]]; then
    KOKORO_VOICES="$KOKORO_PATH/voices-v1.0.bin"
  elif [[ -f "$PWD/kokoro-models/voices-v1.0.bin" ]]; then
    KOKORO_VOICES="$PWD/kokoro-models/voices-v1.0.bin"
  fi
fi

[[ -s "$KOKORO_MODEL" ]] || { echo "ERROR: Kokoro model not found: $KOKORO_MODEL" >&2; exit 1; }
[[ -s "$KOKORO_VOICES" ]] || { echo "ERROR: Kokoro voices not found: $KOKORO_VOICES" >&2; exit 1; }
[[ "$SPEED" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "ERROR: invalid SPEED=$SPEED" >&2; exit 1; }
awk -v s="$SPEED" 'BEGIN{exit !(s>=0.5 && s<=2.0)}' || { echo "ERROR: SPEED must be 0.5-2.0" >&2; exit 1; }
awk -v v="$MUSIC_VOLUME" 'BEGIN{exit !(v>=0 && v<=1)}' || { echo "ERROR: MUSIC_VOLUME must be 0-1" >&2; exit 1; }

SCENE_COUNT="$(jq -r '(.scenes // []) | length' "$JOB_FILE")"
[[ "$SCENE_COUNT" =~ ^[0-9]+$ ]] || { echo "ERROR: invalid scene count" >&2; exit 1; }
(( SCENE_COUNT >= 1 )) || { echo "ERROR: no scenes in job.json" >&2; exit 1; }

printf 'Kokoro: %s\nModel : %s\nVoices: %s\nVoice : %s\nLang  : %s\n' "$KOKORO_BIN" "$KOKORO_MODEL" "$KOKORO_VOICES" "$VOICE" "$LANG_CODE"
printf '%s\n' '======================================' 'PRODUCTION ENGINE' '======================================'

duration() {
  local file="$1"
  [[ -s "$file" ]] || { echo "ERROR: cannot measure missing file: $file" >&2; return 1; }
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file" | awk '{if($1==""||$1=="N/A") exit 1; printf "%.3f",$1}'
}

run_kokoro() {
  local text_file="$1"
  local output_file="$2"
  local log_file="${output_file}.kokoro.log"
  local tmp_file="${output_file}.tmp.wav"
  rm -f "$output_file" "$tmp_file" "$log_file"
  "$KOKORO_BIN" "$text_file" "$tmp_file" --voice "$VOICE" --speed "$SPEED" --lang "$LANG_CODE" --model "$KOKORO_MODEL" --voices "$KOKORO_VOICES" 2>&1 | tee "$log_file"
  [[ -s "$tmp_file" ]] || { echo "ERROR: Kokoro produced no audio." >&2; cat "$log_file" >&2 || true; return 1; }
  ffmpeg -hide_banner -loglevel error -y -i "$tmp_file" -ar 48000 -ac 2 -c:a pcm_s16le "$output_file"
  rm -f "$tmp_file"
  [[ -s "$output_file" ]] || { echo "ERROR: audio normalization failed." >&2; return 1; }
}

generate_voice() {
  local text="$1"
  local output="$2"
  local text_file="${output}.txt"
  [[ -n "${text//[[:space:]]/}" ]] || { echo "ERROR: empty narration." >&2; return 1; }
  printf '%s\n' "$text" > "$text_file"
  run_kokoro "$text_file" "$output"
  rm -f "$text_file"
}

pexels_video() {
  local query="$1"
  local output="$2"
  local api_key="${PEXELS_API_KEY:-}"
  [[ -n "$api_key" ]] || { echo "ERROR: PEXELS_API_KEY is not set." >&2; return 1; }
  local response
  response="$(curl -fsSL --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 120 -H "Authorization: $api_key" --get --data-urlencode "query=$query" --data-urlencode "orientation=portrait" --data-urlencode "size=large" --data-urlencode "per_page=12" https://api.pexels.com/videos/search)"
  local url
  url="$(jq -r '[.videos[]?.video_files[]? | select(.file_type=="video/mp4" and .link!=null and .width!=null and .height!=null) | {link,width,height,pixels:(.width*.height),portrait:(if .height>=.width then 1 else 0 end)}] | sort_by(.portrait,.pixels) | reverse | .[0].link // empty' <<< "$response")"
  [[ -n "$url" ]] || return 1
  curl -fsSL --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 180 -o "$output" "$url"
  [[ -s "$output" ]] || return 1
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$output" >/dev/null
}

render_scene() {
  local source="$1"
  local scene_duration="$2"
  local output="$3"
  local filter
  if [[ "$ANIMATION_ENABLED" == "true" ]]; then
    filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0005,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p"
  else
    filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p"
  fi
  ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$source" -t "$scene_duration" -vf "$filter" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$output"
}

ass_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\{/\\\{}"
  text="${text//\}/\\\}}"
  text="${text//$'\n'/\\N}"
  printf '%s' "$text"
}

seconds_to_ass() {
  local seconds="$1"
  awk -v x="$seconds" 'BEGIN{t=int(x*100+0.5);h=int(t/360000);m=int((t%360000)/6000);s=int((t%6000)/100);c=t%100;printf "%d:%02d:%02d.%02d",h,m,s,c}'
}

create_subtitles() {
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
Style: EN,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,70,70,900,1
Style: AR,DejaVu Sans,52,&H0000FFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,280,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
EOF
  local start_time="0"
  local i
  for ((i=1;i<=SCENE_COUNT;i++)); do
    local text_en="" text_ar="" scene_duration="" end_time="" start_ass="" end_ass=""
    text_en="$(jq -r ".scenes[$((i-1))].text_en // empty" "$JOB_FILE")"
    text_ar="$(jq -r ".scenes[$((i-1))].text_ar // empty" "$JOB_FILE")"
    [[ -n "$text_en" ]] || { echo "ERROR: scene $i missing English text" >&2; return 1; }
    [[ -n "$text_ar" ]] || { echo "ERROR: scene $i missing Arabic text" >&2; return 1; }
    scene_duration="$(duration "$RUN_DIR/audio/scene_${i}.wav")"
    end_time="$(awk -v a="$start_time" -v b="$scene_duration" 'BEGIN{printf "%.3f",a+b}')"
    start_ass="$(seconds_to_ass "$start_time")"
    end_ass="$(seconds_to_ass "$end_time")"
    printf 'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' "$start_ass" "$end_ass" "$(ass_escape "$text_en")" >> "$output"
    printf 'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' "$start_ass" "$end_ass" "$(ass_escape "$text_ar")" >> "$output"
    start_time="$end_time"
  done
}

find_music() {
  local candidate
  local workspace="${GITHUB_WORKSPACE:-}"
  for candidate in "${MUSIC_FILE:-}" "$RUN_DIR/music/music.mp3" "$RUN_DIR/music/background.mp3" "$workspace/assets/music.mp3" "$workspace/assets/background.mp3"; do
    [[ -n "$candidate" && -s "$candidate" ]] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

mix_music() {
  local voice_file="$1"
  local music_file="$2"
  local output_file="$3"
  local voice_duration
  voice_duration="$(duration "$voice_file")"
  ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$music_file" -i "$voice_file" -filter_complex "[0:a]volume=${MUSIC_VOLUME},atrim=0:${voice_duration},asetpts=N/SR/TB[m];[1:a][m]amix=inputs=2:duration=first:normalize=0:dropout_transition=2[mix]" -map "[mix]" -ar 48000 -ac 2 -c:a pcm_s16le "$output_file"
}

: > "$RUN_DIR/video/scenes.txt"
: > "$RUN_DIR/audio/audio_concat.txt"
TOTAL_DURATION="0"

for ((i=1;i<=SCENE_COUNT;i++)); do
  text_en="$(jq -r ".scenes[$((i-1))].text_en // empty" "$JOB_FILE")"
  query="$(jq -r ".scenes[$((i-1))].pexels_query // .query // .topic // \"abstract nature\"" "$JOB_FILE")"
  [[ -n "$text_en" ]] || { echo "ERROR: scene $i has no English narration" >&2; exit 1; }
  audio_file="$RUN_DIR/audio/scene_${i}.wav"
  source_file="$RUN_DIR/downloads/source_${i}.mp4"
  scene_file="$RUN_DIR/scenes/scene_${i}.mp4"

  echo "--- Scene $i/$SCENE_COUNT ---"
  generate_voice "$text_en" "$audio_file"
  scene_duration="$(duration "$audio_file")"

  if ! pexels_video "$query" "$source_file"; then
    echo "WARNING: Pexels returned no usable clip for '$query'; using fallback background." >&2
    ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=0x202020:s=1080x1920:r=30" -t "$scene_duration" -pix_fmt yuv420p "$source_file"
  fi

  render_scene "$source_file" "$scene_duration" "$scene_file"
  printf "file '%s'\n" "$scene_file" >> "$RUN_DIR/video/scenes.txt"
  printf "file '%s'\n" "$audio_file" >> "$RUN_DIR/audio/audio_concat.txt"
  TOTAL_DURATION="$(awk -v a="$TOTAL_DURATION" -v b="$scene_duration" 'BEGIN{printf "%.3f",a+b}')"
done

ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$RUN_DIR/video/scenes.txt" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$RUN_DIR/video/visuals.mp4"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$RUN_DIR/audio/audio_concat.txt" -c:a pcm_s16le -ar 48000 -ac 2 "$RUN_DIR/audio/voice.wav"
create_subtitles

AUDIO_FINAL="$RUN_DIR/audio/voice.wav"
if [[ "$MUSIC_ENABLED" == "true" ]]; then
  MUSIC_PATH="$(find_music || true)"
  if [[ -n "$MUSIC_PATH" ]]; then
    mix_music "$AUDIO_FINAL" "$MUSIC_PATH" "$RUN_DIR/audio/final_mix.wav"
    AUDIO_FINAL="$RUN_DIR/audio/final_mix.wav"
  else
    echo "[MUSIC] No music file found; continuing without background music."
  fi
fi

FINAL="$RUN_DIR/video.mp4"
ffmpeg -hide_banner -loglevel error -y -i "$RUN_DIR/video/visuals.mp4" -i "$AUDIO_FINAL" -vf "ass=$RUN_DIR/subtitles/subtitles.ass" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -ac 2 -shortest -movflags +faststart "$FINAL"
[[ -s "$FINAL" ]] || { echo "ERROR: final video was not created" >&2; exit 1; }

FINAL_DURATION="$(duration "$FINAL")"
FINAL_WIDTH="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$FINAL")"
FINAL_HEIGHT="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$FINAL")"
FINAL_AUDIO_CODEC="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$FINAL")"
awk -v d="$FINAL_DURATION" 'BEGIN{exit !(d>=30 && d<=60)}' || { echo "ERROR: final duration is ${FINAL_DURATION}s; expected 30-60s" >&2; exit 1; }
[[ "$FINAL_WIDTH" == "1080" && "$FINAL_HEIGHT" == "1920" ]] || { echo "ERROR: final resolution is ${FINAL_WIDTH}x${FINAL_HEIGHT}" >&2; exit 1; }
[[ "$FINAL_AUDIO_CODEC" == "aac" ]] || { echo "ERROR: final audio codec is $FINAL_AUDIO_CODEC, expected aac" >&2; exit 1; }

printf '%s\n' '======================================' 'PRODUCTION COMPLETE' '======================================'
printf 'Duration : %ss\nResolution: %sx%s\nAudio     : %s\nOutput    : %s\n' "$FINAL_DURATION" "$FINAL_WIDTH" "$FINAL_HEIGHT" "$FINAL_AUDIO_CODEC" "$FINAL"
