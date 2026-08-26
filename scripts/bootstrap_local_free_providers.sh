#!/usr/bin/env bash
set -Eeuo pipefail

# Free-only provider bootstrap. Ollama runs locally on the GitHub runner.
# FreeLLMAPI is used only when an explicit reachable endpoint and unified key are supplied.
# No paid endpoint is invented or selected automatically.

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
FREELLMAPI_BASE_URL="${FREELLMAPI_BASE_URL:-}"
FREELLMAPI_API_KEY="${FREELLMAPI_API_KEY:-}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

nohup ollama serve >"${RUNNER_TEMP:-/tmp}/ollama.log" 2>&1 </dev/null &

a=false
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then a=true; break; fi
  sleep 2
done
$${a} || { cat "${RUNNER_TEMP:-/tmp}/ollama.log" || true; exit 1; }

echo "OLLAMA_HEALTH=PASS"
echo "Pulling local free model: ${OLLAMA_MODEL}"
ollama pull "${OLLAMA_MODEL}"
curl -fsS http://127.0.0.1:11434/api/show -H 'Content-Type: application/json' -d "{\"model\":\"${OLLAMA_MODEL}\"}" >/dev/null
curl -fsS http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${OLLAMA_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Return exactly OK\"}],\"temperature\":0,\"max_tokens\":8}" >/dev/null
echo "OLLAMA_MODEL_READY=PASS model=${OLLAMA_MODEL}"

if [[ -n "$FREELLMAPI_BASE_URL" ]]; then
  [[ -n "$FREELLMAPI_API_KEY" ]] || { echo 'FREELLMAPI_CONFIG=FAIL missing FREELLMAPI_API_KEY'; exit 1; }
  base="${FREELLMAPI_BASE_URL%/}"
  echo "Checking configured FreeLLMAPI endpoint: ${base}"
  curl -fsS --max-time 20 -H "Authorization: Bearer ${FREELLMAPI_API_KEY}" -H 'Accept: application/json' "${base}/models" >/dev/null
  echo "FREELLMAPI_HEALTH=PASS"
else
  echo "FREELLMAPI_HEALTH=SKIP no FREELLMAPI_BASE_URL configured"
fi
