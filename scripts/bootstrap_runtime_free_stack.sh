#!/usr/bin/env bash
set -Eeuo pipefail

MODEL="${OLLAMA_MODEL:-qwen3:8b}"
TMP="${RUNNER_TEMP:-/tmp}/freellmapi-runtime"
CFG="$TMP/config.json"
mkdir -p "$TMP/data"
chmod 700 "$TMP" "$TMP/data"

if ! command -v ollama >/dev/null 2>&1; then curl -fsSL https://ollama.com/install.sh | sh; fi
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  OLLAMA_HOST=0.0.0.0:11434 nohup ollama serve >"$TMP/ollama.log" 2>&1 </dev/null &
  for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 2; done
fi
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
ollama pull "$MODEL" >/dev/null

python - <<'PY'
import json,os
from pathlib import Path
pairs=[('groq','GROQ_API_KEY'),('google','GEMINI_API_KEY'),('cerebras','CEREBRAS_API_KEY'),('mistral','MISTRAL_API_KEY'),('openrouter','OPENROUTER_API_KEY'),('cloudflare','CLOUDFLARE_API_TOKEN'),('cohere','COHERE_API_KEY'),('huggingface','HF_TOKEN'),('zai','ZAI_API_KEY'),('nvidia','NVIDIA_API_KEY'),('modelscope','MODELSCOPE_API_KEY'),('llm7','LLM7_API_KEY')]
keys=[{'platform':p,'key':os.getenv(e),'label':'ci-free-only'} for p,e in pairs if os.getenv(e,'').strip()]
cfg={'keys':keys,'customProviders':[{'baseUrl':'http://host.docker.internal:11434/v1','label':'Ollama-Local-Free','models':[{'model':os.environ['MODEL'],'displayName':'Ollama local free model','supportsTools':True}]}],'routing':{'strategy':'balanced'}}
Path(os.environ['CFG']).write_text(json.dumps(cfg)+'\n'); print('FREE_CONFIG=PASS')
PY

if ! curl -fsS http://127.0.0.1:3001/api/ping >/dev/null 2>&1; then
  docker rm -f faceless-freellmapi >/dev/null 2>&1 || true
  docker pull ghcr.io/tashfeenahmed/freellmapi:latest >/dev/null
  KEY="$(openssl rand -hex 32)"
  docker run -d --name faceless-freellmapi --add-host host.docker.internal:host-gateway -p 127.0.0.1:3001:3001 -e NODE_ENV=production -e ENCRYPTION_KEY="$KEY" -e PORT=3001 -e HOST=0.0.0.0 -e FREEAPI_CONFIG_PATH=/app/config/config.json -v "$CFG:/app/config/config.json:ro" -v "$TMP/data:/app/server/data" ghcr.io/tashfeenahmed/freellmapi:latest >/dev/null
  for _ in $(seq 1 90); do curl -fsS http://127.0.0.1:3001/api/ping >/dev/null 2>&1 && break; sleep 2; done
fi
curl -fsS http://127.0.0.1:3001/api/ping >/dev/null

STATUS="$(curl -fsS http://127.0.0.1:3001/api/auth/status)"
if python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("needsSetup") else 1)' <<<"$STATUS"; then
  EMAIL="ci-${GITHUB_RUN_ID:-local}@localhost"
  PASSWORD="$(openssl rand -hex 24)"
  BODY="$(python -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "$EMAIL" "$PASSWORD")"
  SESSION="$(curl -fsS -X POST http://127.0.0.1:3001/api/auth/setup -H 'Content-Type: application/json' -d "$BODY" | python -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
else
  echo 'FreeLLMAPI already initialized but no reusable CI session is available; refusing to guess credentials.' >&2
  exit 1
fi

KEY="$(curl -fsS http://127.0.0.1:3001/api/settings/api-key -H "Authorization: Bearer $SESSION" | python -c 'import json,sys; print(json.load(sys.stdin)["apiKey"])')"
[[ "$KEY" == freellmapi-* ]]
curl -fsS http://127.0.0.1:3001/v1/models -H "Authorization: Bearer $KEY" >/dev/null
curl -fsS http://127.0.0.1:3001/v1/chat/completions -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Return exactly OK"}],"temperature":0,"max_tokens":8}' >/dev/null

mkdir -p "$RUN_DIR/ai_router"
{
  echo "FREELLMAPI_BASE_URL=http://127.0.0.1:3001/v1"
  echo "FREELLMAPI_API_KEY=$KEY"
  echo "FREELLMAPI_MODEL=auto"
  echo "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1"
  echo "OLLAMA_MODEL=$MODEL"
} > "$RUN_DIR/ai_router/freellmapi.env"
chmod 600 "$RUN_DIR/ai_router/freellmapi.env"
echo 'FREE_LOCAL_PROVIDER_STACK=PASS'
