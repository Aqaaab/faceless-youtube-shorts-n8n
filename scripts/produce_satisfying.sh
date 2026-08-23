#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUN_DIR="${1:-}"
[[ -n "$RUN_DIR" ]] || { echo "ERROR: Usage: produce_satisfying.sh <RUN_DIR>" >&2; exit 2; }
JOB="$RUN_DIR/job.json"
[[ -s "$JOB" ]] || { echo "ERROR: $JOB missing" >&2; exit 1; }

PEXELS_KEY="${PEXELS_API_KEY:-}"
[[ -n "$PEXELS_KEY" ]] || { echo "ERROR: PEXELS_API_KEY is required" >&2; exit 1; }

PER="$(jq -r '.per // 6' "$JOB")"
HOOK="$(jq -r '.hook // ""' "$JOB")"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUT="$RUN_DIR/video.mp4"

[[ "$PER" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "ERROR: invalid per=$PER" >&2; exit 1; }
awk -v p="$PER" 'BEGIN{exit !(p>0 && p<=30)}' || { echo "ERROR: per must be >0 and <=30 seconds" >&2; exit 1; }

mapfile -t QUERIES < <(jq -r '.queries[]? // empty' "$JOB")
[[ "${#QUERIES[@]}" -gt 0 ]] || { echo "ERROR: no queries in job.json" >&2; exit 1; }

mkdir -p "$RUN_DIR"
i=0
PARTS=()

for Q in "${QUERIES[@]}"; do
  [[ -n "$Q" ]] || continue
  ENC="$(printf '%s' "$Q" | jq -sRr @uri)"
  LINKS="$(curl -fsSL --retry 4 --retry-delay 2 -H "Authorization: $PEXELS_KEY" \
    "https://api.pexels.com/videos/search?query=${ENC}&orientation=portrait&size=large&per_page=15" \
    | jq -r '[.videos[]?.video_files[]? | select(.link!=null and .width!=null and .height!=null and .height>=.width)] | sort_by(.height*.width) | reverse | .[].link' || true)"
  [[ -n "$LINKS" ]] || { echo "INFO: no usable clip for '$Q', skipping" >&2; continue; }

  PICK="$(printf '%s\n' "$LINKS" | sed -n "$(( (i % 3) + 1 ))p")"
  [[ -n "$PICK" ]] || PICK="$(printf '%s\n' "$LINKS" | head -1)"

  RAW="$RUN_DIR/raw_$i.mp4"
  PART="$RUN_DIR/part_$i.mp4"
  if ! curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 20 --max-time 120 "$PICK" -o "$RAW"; then
    echo "INFO: download failed for '$Q'" >&2
    continue
  fi

  if ffmpeg -y -hide_banner -loglevel error -i "$RAW" -t "$PER" \
      -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" \
      -an -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p "$PART"; then
    PARTS+=("$PART")
    i=$((i+1))
  else
    echo "INFO: normalization failed for '$Q'" >&2
  fi
done

[[ "${#PARTS[@]}" -ge 2 ]] || { echo "ERROR: not enough usable clips (${#PARTS[@]})" >&2; exit 1; }

LIST="$RUN_DIR/list.txt"
: > "$LIST"
for p in "${PARTS[@]}"; do
  printf "file '%s'\n" "$p" >> "$LIST"
done

CONCAT="$RUN_DIR/concat.mp4"
ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST" -c copy "$CONCAT" 2>/dev/null \
  || ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST" -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p "$CONCAT"

DUR="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CONCAT")"
[[ -n "$DUR" && "$DUR" != "N/A" ]] || { echo "ERROR: could not determine duration" >&2; exit 1; }

AUDIO_FILTER="lowpass=f=400,volume=0.35,afade=t=in:d=1.5"
if awk -v d="$DUR" 'BEGIN{exit !(d>3)}'; then
  AUDIO_FILTER+=" ,afade=t=out:st=$(awk -v d="$DUR" 'BEGIN{printf "%.3f",d-1.5}'):d=1.5"
fi

if [[ -n "$HOOK" && -f "$FONT" ]]; then
  printf '%s' "$HOOK" > "$RUN_DIR/hook.txt"
  VIDEO_FILTER="[0:v]drawtext=textfile=$RUN_DIR/hook.txt:fontfile=$FONT:fontsize=58:fontcolor=white:borderw=3:bordercolor=black@0.85:box=1:boxcolor=black@0.35:boxborderw=22:x=(w-text_w)/2:y=170[v]"
  MAPV="[v]"
else
  VIDEO_FILTER="[0:v]null[v]"
  MAPV="[v]"
fi

ffmpeg -y -hide_banner -loglevel error \
  -i "$CONCAT" \
  -f lavfi -t "$DUR" -i "anoisesrc=color=brown:amplitude=0.08:sample_rate=44100" \
  -filter_complex "${VIDEO_FILTER};[1:a]${AUDIO_FILTER}[a]" \
  -map "$MAPV" -map "[a]" \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 44100 -ac 2 -movflags +faststart -shortest "$OUT"

[[ -s "$OUT" ]] || { echo "ERROR: satisfying video was not created" >&2; exit 1; }
ffprobe -v error -show_entries format=duration -show_entries stream=width,height,codec_name -of json "$OUT"
printf '%s\n' "Satisfying video complete: $OUT"
