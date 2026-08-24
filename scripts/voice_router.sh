#!/usr/bin/env bash
set -Eeuo pipefail
text_file="${1:-}"
out_file="${2:-}"
shift 2 || true
if [[ -z "$text_file" || -z "$out_file" ]]; then echo 'usage: voice_router.sh TEXT_FILE OUTPUT_WAV [ignored kokoro args...]' >&2; exit 2; fi
if python "$GITHUB_WORKSPACE/scripts/voice_router.py" "$text_file" "$out_file"; then exit 0; fi
KOKORO_BIN_REAL="${KOKORO_REAL_BIN:-$(command -v kokoro-tts 2>/dev/null || true)}"
[[ -n "$KOKORO_BIN_REAL" ]] || { echo 'ERROR: no TTS provider succeeded and kokoro-tts is unavailable' >&2; exit 1; }
VOICE="${VOICE:-af_bella}"
SPEED="${SPEED:-0.90}"
LANG_CODE="${LANG_CODE:-${KOKORO_LANG:-en-us}}"
KOKORO_MODEL="${KOKORO_MODEL:-${KOKORO_PATH:-}/kokoro-v1.0.onnx}"
KOKORO_VOICES="${KOKORO_VOICES:-${KOKORO_PATH:-}/voices-v1.0.bin}"
tmp="${out_file}.kokoro.tmp.wav"
rm -f "$out_file" "$tmp"
"$KOKORO_BIN_REAL" "$text_file" "$tmp" --voice "$VOICE" --speed "$SPEED" --lang "$LANG_CODE" --model "$KOKORO_MODEL" --voices "$KOKORO_VOICES"
ffmpeg -hide_banner -loglevel error -y -i "$tmp" -ar 48000 -ac 2 -c:a pcm_s16le "$out_file"
rm -f "$tmp"
[[ -s "$out_file" ]] || exit 1
echo 'VOICE_PROVIDER=Kokoro'
