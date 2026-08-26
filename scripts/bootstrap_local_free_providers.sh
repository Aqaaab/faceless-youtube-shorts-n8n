#!/usr/bin/env bash
set -Eeuo pipefail

# This bootstrap is intentionally free-only. Ollama runs locally on the GitHub runner.
# FreeLLMAPI is used only when an explicit, reachable FREELLMAPI_BASE_URL is supplied.
# We never invent or silently switch to a paid endpoint.

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"
FREELLMAPI_BASE_URL="${FREELLMAPI_BASE_URL:-}"
FREELLMAPI_API_KEY="${FREELLMAPI_API_KEY:-}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

ollama serve >"${RUNNER_TEMP:-/tmp}/ollama.log" 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
echo "OLLAMA_HEALTH=PASS"

echo "Pulling local free model: ${OLLAMA_MODEL}"
ollama pull "${OLLAMA_MODEL}"
curl -fsS http://127.0.0.1:11434/api/show -H 'Content-Type: application/json' -d "{\"model\":\"${OLLAMA_MODEL}\"}" >/dev/null
echo "OLLAMA_MODEL_READY=PASS model=${OLLAMA_MODEL}"

if [[ -n "$FREELLMAPI_BASE_URL" ]]; then
  if [[ -z "$FREELLMAPI_API_KEY" ]]; then
    echo "FREELLMAPI_CONFIG=FAIL missing FREELLMAPI_API_KEY"
    exit 1
  fi
  base="${FREELLMAPI_BASE_URL%/}"
  echo "Checking configured FreeLLMAPI endpoint: ${base}"
  curl -fsS --max-time 20 \
    -H "Authorization: Bearer ${FREELLMAPI_API_KEY}" \
    -H 'Accept: application/json' \
    "${base}/models" >/dev/null
  echo "FREELLMAPI_HEALTH=PASS"
else
  echo "FREELLMAPI_HEALTH=SKIP no FREELLMAPI_BASE_URL configured"
fi
