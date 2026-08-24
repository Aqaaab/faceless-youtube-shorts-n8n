#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
RUN_DIR="${RUN_DIR:-${1:-/data/job}}"; JOB_FILE="$RUN_DIR/job.json"
ANIMATION_ENABLED="${ANIMATION_ENABLED:-true}"; MUSIC_ENABLED="${MUSIC_ENABLED:-true}"; MUSIC_VOLUME="${MUSIC_VOLUME:-0.08}"
MIN_SCENES="${MIN_SCENES:-5}"; MAX_SCENES="${MAX_SCENES:-10}"
[[ -f "$JOB_FILE" ]] || { echo "ERROR: missing $JOB_FILE" >&2; exit 1; }
for bin in ffmpeg ffprobe jq awk sed python; do command -v "$bin" >/dev/null || { echo "ERROR: missing $bin" >&2; exit 1; }; done
[[ -f "$GITHUB_WORKSPACE/scripts/visual_candidate_select.py" ]] || { echo "ERROR: visual candidate selector is missing" >&2; exit 1; }
[[ -f "$GITHUB_WORKSPACE/scripts/voice_router.sh" ]] || { echo "ERROR: voice router is missing" >&2; exit 1; }
mkdir -p "$RUN_DIR/audio" "$RUN_DIR/scenes" "$RUN_DIR/downloads" "$RUN_DIR/subtitles" "$RUN_DIR/video" "$RUN_DIR/music"
SCENE_COUNT="$(jq -r '(.scenes // []) | length' "$JOB_FILE")"; [[ "$SCENE_COUNT" -ge "$MIN_SCENES" && "$SCENE_COUNT" -le "$MAX_SCENES" ]] || { echo "ERROR: scene count $SCENE_COUNT outside $MIN_SCENES-$MAX_SCENES" >&2; exit 1; }
words(){ printf '%s' "$1" | grep -Eo "[A-Za-z][A-Za-z0-9'-]*" | wc -l | tr -d ' '; }; duration(){ ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1"; }
ass_escape(){ local x="$1"; x="${x//\\/\\\\}"; x="${x//\{/\\\{}"; x="${x//\}/\\\}}"; x="${x//$'\n'/\\N}"; printf '%s' "$x"; }; ass_time(){ awk -v x="$1" 'BEGIN{t=int(x*100+0.5);printf "%d:%02d:%02d.%02d",int(t/360000),int((t%360000)/6000),int((t%6000)/100),t%100}'; }
wrap_ar(){ awk -v text="$1" -v max=30 'BEGIN{n=split(text,w,/ +/);line="";out="";for(i=1;i<=n;i++){if(line=="")line=w[i];else if(length(line)+1+length(w[i])<=max)line=line" "w[i];else{out=out (out==""?"":"\\N") line;line=w[i]}}if(line!="")out=out (out==""?"":"\\N") line;print out}'; }
render_scene(){ local src="$1" dur="$2" out="$3" vf; if [[ "$ANIMATION_ENABLED" == "true" ]];then vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0005,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p";else vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p";fi; ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$src" -t "$dur" -vf "$vf" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$out"; }
cat > "$RUN_DIR/subtitles/subtitles.ass" <<'EOF'
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: AR,DejaVu Sans,48,&H0000FFFF,&H0000FFFF,&H00101010,&HE6000000,1,0,0,0,100,100,0,0,3,2,1,2,70,70,500,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
EOF
: > "$RUN_DIR/video/scenes.txt"; : > "$RUN_DIR/audio/audio_concat.txt"; start=0
for ((i=1;i<=SCENE_COUNT;i++)); do
 idx=$((i-1)); en="$(jq -r ".scenes[$idx].text_en // empty" "$JOB_FILE")"; ar="$(jq -r ".scenes[$idx].text_ar // empty" "$JOB_FILE")"; query="$(jq -r ".scenes[$idx].pexels_query // empty" "$JOB_FILE")"; subject="$(jq -r ".scenes[$idx].visual_subject // empty" "$JOB_FILE")"; [[ -n "$en" && -n "$ar" && -n "$query" && -n "$subject" ]] || { echo "ERROR: scene $i missing required fields" >&2; exit 1; }; [[ "$(words "$en")" -ge 8 && "$(words "$en")" -le 18 ]] || { echo "ERROR: scene $i English narration length invalid" >&2; exit 1; }
 text_file="$RUN_DIR/audio/scene_${i}.txt"; audio="$RUN_DIR/audio/scene_${i}.wav"; source="$RUN_DIR/downloads/source_${i}.mp4"; scene="$RUN_DIR/scenes/scene_${i}.mp4"; printf '%s\n' "$en" > "$text_file"; echo "--- Scene $i/$SCENE_COUNT: query='$query' subject='$subject' ---"; bash "$GITHUB_WORKSPACE/scripts/voice_router.sh" "$text_file" "$audio"; [[ -s "$audio" ]] || { echo "ERROR: no voice audio for scene $i" >&2; exit 1; }; dur="$(duration "$audio")"; python "$GITHUB_WORKSPACE/scripts/visual_candidate_select.py" "$query" "$subject" "$en" "$source"; [[ -s "$source" ]] || { echo "ERROR: no visual provider succeeded for scene $i" >&2; exit 1; }; render_scene "$source" "$dur" "$scene"; printf "file '%s'\n" "$scene" >> "$RUN_DIR/video/scenes.txt"; printf "file '%s'\n" "$audio" >> "$RUN_DIR/audio/audio_concat.txt"; end="$(awk -v a="$start" -v b="$dur" 'BEGIN{printf "%.3f",a+b}')"; wrapped="$(wrap_ar "$ar")"; printf 'Dialogue: 0,%s,%s,AR,,0,0,0,,{\\fs48}%s\n' "$(ass_time "$start")" "$(ass_time "$end")" "$(ass_escape "$wrapped")" >> "$RUN_DIR/subtitles/subtitles.ass"; start="$end"
done
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$RUN_DIR/video/scenes.txt" -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart "$RUN_DIR/video/visuals.mp4"; ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$RUN_DIR/audio/audio_concat.txt" -c:a pcm_s16le -ar 48000 -ac 2 "$RUN_DIR/audio/voice.wav"; AUDIO_FINAL="$RUN_DIR/audio/voice.wav"
if [[ "$MUSIC_ENABLED" == "true" ]]; then MUSIC_PATH="${MUSIC_FILE:-}"; for candidate in "$MUSIC_PATH" "$RUN_DIR/music/music.mp3" "$RUN_DIR/music/background.mp3" "${GITHUB_WORKSPACE:-}/assets/music.mp3"; do if [[ -n "$candidate" && -s "$candidate" ]];then MUSIC_PATH="$candidate";break;fi;done; if [[ -n "${MUSIC_PATH:-}" && -s "$MUSIC_PATH" ]];then vd="$(duration "$AUDIO_FINAL")"; ffmpeg -hide_banner -loglevel error -y -stream_loop -1 -i "$MUSIC_PATH" -i "$AUDIO_FINAL" -filter_complex "[0:a]volume=${MUSIC_VOLUME},atrim=0:${vd},asetpts=N/SR/TB[m];[1:a][m]amix=inputs=2:duration=first:normalize=0:dropout_transition=2[a]" -map "[a]" -ar 48000 -ac 2 -c:a pcm_s16le "$RUN_DIR/audio/final_mix.wav"; AUDIO_FINAL="$RUN_DIR/audio/final_mix.wav";fi;fi
ffmpeg -hide_banner -loglevel error -y -i "$RUN_DIR/video/visuals.mp4" -i "$AUDIO_FINAL" -vf "ass=$RUN_DIR/subtitles/subtitles.ass" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart "$RUN_DIR/video.mp4"; [[ -s "$RUN_DIR/video.mp4" ]] || { echo "ERROR: final video was not created" >&2; exit 1; }; jq -n --arg mode "english_voice_arabic_subtitles" --argjson scenes "$SCENE_COUNT" '{subtitle_mode:$mode,scenes:$scenes,english_spoken:true,english_overlay:false,arabic_overlay:true}' > "$RUN_DIR/render_contract.json"; echo "Production complete: $RUN_DIR/video.mp4; scenes=$SCENE_COUNT"