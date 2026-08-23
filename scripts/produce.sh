#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

# YouTube Shorts production engine.
# Input : <RUN_DIR>/job.json
# Output: <RUN_DIR>/video.mp4

RUN_DIR="${1:-${RUN_DIR:-}}"
[[ -n "$RUN_DIR" ]] || { echo "ERROR: RUN_DIR is required."; exit 2; }
RUN_DIR="$(realpath -m "$RUN_DIR")"
JOB_JSON="$RUN_DIR/job.json"
[[ -f "$JOB_JSON" ]] || { echo "ERROR: Missing job.json: $JOB_JSON"; exit 1; }

export PATH="${HOME}/.local/bin:${PATH}"

for bin in ffmpeg ffprobe jq curl awk sed realpath; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: Required command not found: $bin"; exit 1; }
done

PEXELS_API_KEY="${PEXELS_API_KEY:-}"
[[ -n "$PEXELS_API_KEY" ]] || { echo "ERROR: PEXELS_API_KEY is not set."; exit 1; }

mkdir -p "$RUN_DIR/scenes" "$RUN_DIR/audio" "$RUN_DIR/video" "$RUN_DIR/subtitles" "$RUN_DIR/downloads" "$RUN_DIR/music"

VOICE="$(jq -r '.voice // "af_bella"' "$JOB_JSON")"
SPEED="$(jq -r '.speed // 1.0' "$JOB_JSON")"
LANG_CODE="$(jq -r '.lang // .language // "en-us"' "$JOB_JSON")"
MUSIC_ENABLED="$(jq -r 'if .music == false then "false" else "true" end' "$JOB_JSON")"
MUSIC_VOLUME="$(jq -r '.music_volume // 0.10' "$JOB_JSON")"
ANIMATION_ENABLED="$(jq -r 'if .animation == false then "false" else "true" end' "$JOB_JSON")"
ADS_ENABLED="$(jq -r 'if .ads == true then "true" else "false" end' "$JOB_JSON")"

# Ads are intentionally disabled until a real ad asset/placement contract is configured.
if [[ "$ADS_ENABLED" == "true" ]]; then
  echo "ERROR: ads=true is not supported by this renderer yet. Set ads=false."
  exit 1
fi

awk -v speed="$SPEED" 'BEGIN { exit !(speed >= 0.5 && speed <= 2.0) }' || { echo "ERROR: SPEED must be between 0.5 and 2.0."; exit 1; }
awk -v volume="$MUSIC_VOLUME" 'BEGIN { exit !(volume >= 0 && volume <= 1) }' || { echo "ERROR: MUSIC_VOLUME must be between 0 and 1."; exit 1; }

SCENE_COUNT="$(jq '.scenes | length' "$JOB_JSON")"
[[ "$SCENE_COUNT" =~ ^[0-9]+$ ]] || { echo "ERROR: Invalid scene count."; exit 1; }
(( SCENE_COUNT >= 1 )) || { echo "ERROR: No scenes found in job.json."; exit 1; }

KOKORO_BIN="${KOKORO_BIN:-$(command -v kokoro-tts 2>/dev/null || true)}"
KOKORO_PATH="${KOKORO_PATH:-}"
KOKORO_MODEL="${KOKORO_MODEL:-}"
KOKORO_VOICES="${KOKORO_VOICES:-}"

if [[ -z "$KOKORO_MODEL" && -n "$KOKORO_PATH" && -f "$KOKORO_PATH/kokoro-v1.0.onnx" ]]; then KOKORO_MODEL="$KOKORO_PATH/kokoro-v1.0.onnx"; fi
if [[ -z "$KOKORO_VOICES" && -n "$KOKORO_PATH" && -f "$KOKORO_PATH/voices-v1.0.bin" ]]; then KOKORO_VOICES="$KOKORO_PATH/voices-v1.0.bin"; fi
if [[ -z "$KOKORO_MODEL" && -f "$PWD/kokoro-models/kokoro-v1.0.onnx" ]]; then KOKORO_MODEL="$PWD/kokoro-models/kokoro-v1.0.onnx"; fi
if [[ -z "$KOKORO_VOICES" && -f "$PWD/kokoro-models/voices-v1.0.bin" ]]; then KOKORO_VOICES="$PWD/kokoro-models/voices-v1.0.bin"; fi

[[ -n "$KOKORO_BIN" && -x "$KOKORO_BIN" ]] || { echo "ERROR: kokoro-tts CLI was not found/executable."; exit 1; }
[[ -n "$KOKORO_MODEL" && -s "$KOKORO_MODEL" ]] || { echo "ERROR: KOKORO_MODEL was not found."; exit 1; }
[[ -n "$KOKORO_VOICES" && -s "$KOKORO_VOICES" ]] || { echo "ERROR: KOKORO_VOICES was not found."; exit 1; }

export KOKORO_MODEL KOKORO_VOICES

echo "Kokoro: $KOKORO_BIN"
echo "Model : $KOKORO_MODEL"
echo "Voice : $VOICE"
echo "Lang  : $LANG_CODE"

duration() {
  local file="$1"
  [[ -s "$file" ]] || { echo "ERROR: Cannot measure missing file: $file" >&2; return 1; }
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file" | awk '{ if ($1=="" || $1=="N/A") exit 1; printf "%.3f", $1 }'
}

run_kokoro() {
  local text_file="$1" output_file="$2" log_file="${output_file}.kokoro.log" tmp_file="${output_file}.tmp.wav"
  rm -f "$output_file" "$tmp_file" "$log_file"
  "$KOKORO_BIN" "$text_file" "$tmp_file" --voice "$VOICE" --speed "$SPEED" --lang "$LANG_CODE" --model "$KOKORO_MODEL" --voices "$KOKORO_VOICES" 2>&1 | tee "$log_file"
  [[ -s "$tmp_file" ]] || { echo "ERROR: Kokoro produced no audio."; cat "$log_file" >&2 || true; return 1; }
  ffmpeg -hide_banner -loglevel error -y -i "$tmp_file" -ar 48000 -ac 2 -c:a pcm_s16le "$output_file"
  rm -f "$tmp_file"
  [[ -s "$output_file" ]] || { echo "ERROR: Audio normalization failed."; return 1; }
}

generate_voice() {
  local text="$1" output="$2" text_file="${output}.txt"
  [[ -n "${text//[[:space:]]/}" ]] || { echo "ERROR: Empty narration."; return 1; }
  printf '%s\n' "$text" > "$text_file"
  run_kokoro "$text_file" "$output"
  rm -f "$text_file"
}

pexels_video() {
  local query="$1" index="$2" json_file="$RUN_DIR/downloads/pexels_${index}.json" output_file="$RUN_DIR/downloads/source_${index}.mp4"
  rm -f "$json_file" "$output_file"
  curl -fsSL --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 120 \
    -H "Authorization: $PEXELS_API_KEY" --get "https://api.pexels.com/videos/search" \
    --data-urlencode "query=$query" --data-urlencode "orientation=portrait" --data-urlencode "size=medium" --data-urlencode "per_page=15" > "$json_file"
  local url
  url="$(jq -r '[.videos[]? | .video_files[]? | select(.file_type=="video/mp4" and .link!=null and .width!=null and .height!=null) | {link:.link,width:.width,height:.height,pixels:(.width*.height),portrait:(if .height>=.width then 1 else 0 end)}] | sort_by(.portrait,.pixels) | reverse | .[0].link // empty' "$json_file")"
  [[ -n "$url" ]] || { echo "ERROR: No usable Pexels video found for: $query"; jq '.' "$json_file" >&2 || true; return 1; }
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 180 -o "$output_file" "$url"
  [[ -s "$output_file" ]] || { echo "ERROR: Pexels download is empty."; return 1; }
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$output_file" >/dev/null || { echo "ERROR: Invalid Pexels video."; return 1; }
}

make_scene_video() {
  local source="$1" scene_duration="$2" output="$3" filter
  if [[ "$ANIMATION_ENABLED" == "true" ]]; then
    filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p"
  else
    filter="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p"
  fi
  ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$source" -t "$scene_duration" -vf "$filter" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$output"
  [[ -s "$output" ]] || { echo "ERROR: Scene video was not created."; return 1; }
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
  awk -v x="$1" 'BEGIN { total=int(x*100+0.5); h=int(total/360000); m=int((total%360000)/6000); s=int((total%6000)/100); c=total%100; printf "%d:%02d:%02d.%02d",h,m,s,c }'
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
Style: EN,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,70,70,900,1
Style: AR,DejaVu Sans,52,&H0000FFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,280,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
EOF
  local start_time="0"
  for ((i=1;i<=SCENE_COUNT;i++)); do
    local text arabic scene_duration end_time start_ass end_ass en ar
    text="$(jq -r ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" "$JOB_JSON")"
    arabic="$(jq -r ".scenes[$((i-1))].text_ar // empty" "$JOB_JSON")"
    [[ -n "$text" ]] || { echo "ERROR: Scene $i missing English subtitle."; exit 1; }
    [[ -n "$arabic" ]] || { echo "ERROR: Scene $i missing Arabic subtitle."; exit 1; }
    scene_duration="$(duration "$RUN_DIR/audio/scene_${i}.wav")"
    end_time="$(awk -v s="$start_time" -v d="$scene_duration" 'BEGIN{printf "%.3f",s+d}')"
    start_ass="$(seconds_to_ass "$start_time")"
    end_ass="$(seconds_to_ass "$end_time")"
    en="$(ass_escape "$text")"; ar="$(ass_escape "$arabic")"
    printf 'Dialogue: 0,%s,%s,EN,,0,0,0,,%s\n' "$start_ass" "$end_ass" "$en" >> "$output"
    printf 'Dialogue: 1,%s,%s,AR,,0,0,0,,%s\n' "$start_ass" "$end_ass" "$ar" >> "$output"
    start_time="$end_time"
  done
}

find_music() {
  [[ -n "${MUSIC_FILE:-}" && -f "$MUSIC_FILE" ]] && { printf '%s\n' "$MUSIC_FILE"; return 0; }
  local dir="${MUSIC_DIR:-$RUN_DIR/music}" file
  [[ -d "$dir" ]] || return 1
  for file in "$dir"/*.mp3 "$dir"/*.wav "$dir"/*.m4a "$dir"/*.aac; do
    [[ -f "$file" ]] && { printf '%s\n' "$file"; return 0; }
  done
  return 1
}

add_music() {
  local voice="$1" music="$2" output="$3" volume="$4" voice_duration
  voice_duration="$(duration "$voice")"
  ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$music" -i "$voice" \
    -filter_complex "[0:a]volume=${volume},atrim=0:${voice_duration},asetpts=N/SR/TB[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]" \
    -map "[mix]" -ar 48000 -ac 2 -c:a pcm_s16le "$output"
  [[ -s "$output" ]] || { echo "ERROR: Music mix failed."; return 1; }
}

concat_scenes() {
  local list="$RUN_DIR/video/scenes.txt"
  : > "$list"
  for ((i=1;i<=SCENE_COUNT;i++)); do printf "file '%s'\n" "$RUN_DIR/scenes/scene_${i}.mp4" >> "$list"; done
  ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$list" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$RUN_DIR/video/visuals.mp4"
  [[ -s "$RUN_DIR/video/visuals.mp4" ]] || { echo "ERROR: Scene concatenation failed."; return 1; }
}

build_final_video() {
  local visuals="$RUN_DIR/video/visuals.mp4" voice="$RUN_DIR/audio/voice.wav" subtitles="$RUN_DIR/subtitles/subtitles.ass" output="$RUN_DIR/video.mp4" audio="$voice"
  [[ -s "$visuals" ]] || { echo "ERROR: Missing visuals."; return 1; }
  [[ -s "$voice" ]] || { echo "ERROR: Missing voice."; return 1; }
  if [[ "$MUSIC_ENABLED" == "true" ]]; then
    local music="$(find_music || true)"
    if [[ -n "$music" && -s "$music" ]]; then
      local mixed="$RUN_DIR/audio/final_mix.wav"
      add_music "$voice" "$music" "$mixed" "$MUSIC_VOLUME"
      audio="$mixed"
    else
      echo "[MUSIC] No music file found. Continuing without music."
    fi
  fi
  rm -f "$output"
  if [[ -s "$subtitles" ]]; then
    ffmpeg -hide_banner -loglevel error -y -i "$visuals" -i "$audio" -vf "ass=$subtitles" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -ac 2 -shortest -movflags +faststart "$output"
  else
    ffmpeg -hide_banner -loglevel error -y -i "$visuals" -i "$audio" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -ac 2 -shortest -movflags +faststart "$output"
  fi
  [[ -s "$output" ]] || { echo "ERROR: Final video was not created."; return 1; }
}

validate_final_video() {
  local file="$1" duration_value width height audio_codec
  duration_value="$(duration "$file")"
  awk -v d="$duration_value" 'BEGIN{exit !(d>=30 && d<=60)}' || { echo "ERROR: Final video duration must be 30-60s. Actual: ${duration_value}s"; return 1; }
  width="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$file")"
  height="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$file")"
  audio_codec="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$file")"
  [[ "$width" == "1080" && "$height" == "1920" ]] || { echo "ERROR: Final video must be 1080x1920. Actual: ${width}x${height}"; return 1; }
  [[ "$audio_codec" == "aac" ]] || { echo "ERROR: Final audio must be AAC. Actual: $audio_codec"; return 1; }
  echo "Final video validated: ${duration_value}s, ${width}x${height}, audio=${audio_codec}"
}

echo "======================================"
echo "PRODUCTION ENGINE"
echo "======================================"
TOTAL_DURATION="0"

for ((i=1;i<=SCENE_COUNT;i++)); do
  text_en="$(jq -r ".scenes[$((i-1))].text_en // .scenes[$((i-1))].text // empty" "$JOB_JSON")"
  text_ar="$(jq -r ".scenes[$((i-1))].text_ar // empty" "$JOB_JSON")"
  query="$(jq -r ".scenes[$((i-1))].pexels_query // .scenes[$((i-1))].query // .scenes[$((i-1))].visual_query // empty" "$JOB_JSON")"
  [[ -n "$text_en" ]] || { echo "ERROR: Scene $i has no English text."; exit 1; }
  [[ -n "$text_ar" ]] || { echo "ERROR: Scene $i has no Arabic text."; exit 1; }
  [[ -n "$query" ]] || query="abstract technology"
  voice_file="$RUN_DIR/audio/scene_${i}.wav"; scene_file="$RUN_DIR/scenes/scene_${i}.mp4"; source_file="$RUN_DIR/downloads/source_${i}.mp4"
  generate_voice "$text_en" "$voice_file"
  scene_duration="$(duration "$voice_file")"
  pexels_video "$query" "$i"
  make_scene_video "$source_file" "$scene_duration" "$scene_file"
  TOTAL_DURATION="$(awk -v a="$TOTAL_DURATION" -v b="$scene_duration" 'BEGIN{printf "%.3f",a+b}')"
done

echo "Total narration duration: ${TOTAL_DURATION}s"
create_ass
concat_scenes

voice_all="$RUN_DIR/audio/voice.wav"
: > "$RUN_DIR/audio/audio_concat.txt"
for ((i=1;i<=SCENE_COUNT;i++)); do printf "file '%s'\n" "$RUN_DIR/audio/scene_${i}.wav" >> "$RUN_DIR/audio/audio_concat.txt"; done
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$RUN_DIR/audio/audio_concat.txt" -c:a pcm_s16le -ar 48000 -ac 2 "$voice_all"
[[ -s "$voice_all" ]] || { echo "ERROR: Failed to concatenate narration."; exit 1; }

build_final_video
validate_final_video "$RUN_DIR/video.mp4"

echo "PRODUCTION COMPLETE: $RUN_DIR/video.mp4"
duration "$RUN_DIR/video.mp4"
du -h "$RUN_DIR/video.mp4" | awk '{print $1}'
exit 0
