#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${RUN_DIR:-${1:-/data/job}}"
JOB_FILE="${JOB_FILE:-$RUN_DIR/job.json}"
KOKORO_BIN="${KOKORO_BIN:-kokoro-tts}"
KOKORO_MODEL="${KOKORO_MODEL:-$PWD/kokoro-models/kokoro-v1.0.onnx}"
KOKORO_VOICES="${KOKORO_VOICES:-$PWD/kokoro-models/voices-v1.0.bin}"
VOICE="${VOICE:-af_bella}"
LANG_CODE="${LANG_CODE:-en-us}"
SPEED="${SPEED:-1.0}"

[[ -f "$JOB_FILE" ]] || { echo "ERROR: job.json not found: $JOB_FILE" >&2; exit 1; }
mkdir -p "$RUN_DIR"

duration() {
  local file="$1"
  [[ -s "$file" ]] || { echo "ERROR: Cannot measure missing file: $file" >&2; return 1; }
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file" | awk '{ if ($1=="" || $1=="N/A") exit 1; printf "%.3f", $1 }'
}

run_kokoro() {
  local text_file="$1"
  local output_file="$2"
  local log_file="${output_file}.kokoro.log"
  local tmp_file="${output_file}.tmp.wav"
  rm -f "$output_file" "$tmp_file" "$log_file"
  "$KOKORO_BIN" "$text_file" "$tmp_file" --voice "$VOICE" --speed "$SPEED" --lang "$LANG_CODE" --model "$KOKORO_MODEL" --voices "$KOKORO_VOICES" 2>&1 | tee "$log_file"
  [[ -s "$tmp_file" ]] || { echo "ERROR: Kokoro produced no audio."; cat "$log_file" >&2 || true; return 1; }
  ffmpeg -hide_banner -loglevel error -y -i "$tmp_file" -ar 48000 -ac 2 -c:a pcm_s16le "$output_file"
  rm -f "$tmp_file"
  [[ -s "$output_file" ]] || { echo "ERROR: Audio normalization failed."; return 1; }
}

generate_voice() {
  local text="$1"
  local output="$2"
  local text_file="${output}.txt"
  [[ -n "${text//[[:space:]]/}" ]] || { echo "ERROR: Empty narration."; return 1; }
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
  response="$(curl -fsSL --retry 3 -H "Authorization: $api_key" --get --data-urlencode "query=$query" --data-urlencode "orientation=portrait" --data-urlencode "size=large" --data-urlencode "per_page=10" https://api.pexels.com/videos/search)"
  local url
  url="$(jq -r '.videos[0].video_files | map(select(.width >= 720 and .height >= 1280)) | sort_by(.width) | reverse | .[0].link // empty' <<<"$response")"
  [[ -n "$url" ]] || { echo "ERROR: No suitable Pexels video found for: $query" >&2; return 1; }
  curl -fsSL --retry 3 -o "$output" "$url"
  [[ -s "$output" ]] || { echo "ERROR: Pexels download failed." >&2; return 1; }
}

echo "Kokoro: $KOKORO_BIN"
echo "Model : $KOKORO_MODEL"
echo "Voice : $VOICE"
echo "Lang  : $LANG_CODE"
echo "======================================"
echo "PRODUCTION ENGINE"
echo "======================================"

tmpdir="$RUN_DIR/work"
mkdir -p "$tmpdir"

narration="$(jq -r '.narration // .script // .voiceover // empty' "$JOB_FILE")"
[[ -n "${narration//[[:space:]]/}" ]] || { echo "ERROR: job.json contains no narration/script/voiceover." >&2; exit 1; }

audio="$RUN_DIR/narration.wav"
generate_voice "$narration" "$audio"

echo "Narration: $audio ($(duration "$audio")s)"

query="$(jq -r '.pexels_query // .query // .visual_query // ""' "$JOB_FILE")"
video="$RUN_DIR/source.mp4"
if [[ -n "$query" ]]; then
  pexels_video "$query" "$video"
else
  echo "WARNING: No Pexels query in job.json; using fallback black background."
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i color=c=black:s=1080x1920:r=30 -t "$(duration "$audio")" -pix_fmt yuv420p "$video"
fi

final="$RUN_DIR/video.mp4"
ffmpeg -hide_banner -loglevel error -y \
  -stream_loop -1 -i "$video" \
  -i "$audio" \
  -map 0:v:0 -map 1:a:0 \
  -t "$(duration "$audio")" \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p" \
  -c:v libx264 -preset medium -crf 21 -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  "$final"

[[ -s "$final" ]] || { echo "ERROR: Final video was not created." >&2; exit 1; }
ffprobe -v error -show_entries format=duration -show_entries stream=width,height,codec_name -of json "$final"
echo "======================================"
echo "PRODUCTION COMPLETE"
echo "$final"
