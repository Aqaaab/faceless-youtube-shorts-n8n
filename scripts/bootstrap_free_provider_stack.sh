#!/usr/bin/env bash
set -Eeuo pipefail

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
FREELLMAPI_IMAGE="${FREELLMAPI_IMAGE:-ghcr.io/tashfeenahmed/freellmapi:latest}"
CONTAINER="faceless-freellmapi"
BASE="http://127.0.0.1:3001/v1"
TMP="${RUNNER_TEMP:-/tmp}/freellmapi"
mkdir -p "$TMP/data"
chmod 700 "$TMP" "$TMP/data"

if ! command -v ollama >/dev/null 2>&1; then curl -fsSL https://ollama.com/install.sh | sh; fi
export OLLAMA_HOST="0.0.0.0:11434"
nohup ollama serve >"$TMP/ollama.log" 2>&1 </dev/null &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true; docker rm -f "$CONTAINER" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 2; done
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
ollama pull "$OLLAMA_MODEL"
curl -fsS http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"$OLLAMA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Return exactly OK\"}],\"temperature\":0,\"max_tokens\":8}" >/dev/null
echo 'OLLAMA_STACK=PASS'

export FREELLMAPI_CONFIG="$TMP/config.json"
python - <<'PY'
import json, os
from pathlib import Path
pairs=[('groq','GROQ_API_KEY'),('google','GEMINI_API_KEY'),('cerebras','CEREBRAS_API_KEY'),('mistral','MISTRAL_API_KEY'),('openrouter','OPENROUTER_API_KEY'),('cloudflare','CLOUDFLARE_API_TOKEN'),('cohere','COHERE_API_KEY'),('huggingface','HF_TOKEN'),('zai','ZAI_API_KEY'),('nvidia','NVIDIA_API_KEY'),('modelscope','MODELSCOPE_API_KEY'),('llm7','LLM7_API_KEY')]
keys=[{'platform':p,'key':os.getenv(e),'label':'ci-free-only'} for p,e in pairs if os.getenv(e,'').strip()]
cfg={'keys':keys,'customProviders':[{'baseUrl':'http://host.docker.internal:11434/v1','label':'Ollama-Local-Free','models':[{'model':os.environ['OLLAMA_MODEL'],'displayName':'Ollama local free model','supportsTools':True}]}],'routing':{'strategy':'balanced'}}
Path(os.environ['FREELLMAPI_CONFIG']).write_text(json.dumps(cfg)+'\n'); os.chmod(os.environ['FREELLMAPI_CONFIG'],0o600)
print(f'FREELLMAPI_CONFIG=PASS providers={len(keys)}')
PY

# Docker is the supported FreeLLMAPI deployment path. The config is mounted read-only.
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
KEY="$(openssl rand -hex 32)"
docker pull "$FREELLMAPI_IMAGE" >/dev/null
docker run -d --name "$CONTAINER" --add-host host.docker.internal:host-gateway -p 127.0.0.1:3001:3001 -e NODE_ENV=production -e ENCRYPTION_KEY="$KEY" -e PORT=3001 -e HOST=0.0.0.0 -e FREEAPI_CONFIG_PATH=/app/config/config.json -v "$FREELLMAPI_CONFIG:/app/config/config.json:ro" -v "$TMP/data:/app/server/data" "$FREELLMAPI_IMAGE" >/dev/null
for _ in $(seq 1 90); do curl -fsS http://127.0.0.1:3001/api/ping >/dev/null 2>&1 && break; sleep 2; done
curl -fsS http://127.0.0.1:3001/api/ping >/dev/null

# First-run setup is explicitly allowed from loopback; use a throwaway CI account.
export CI_EMAIL="ci-${GITHUB_RUN_ID:-local}@localhost"
export CI_PASSWORD="$(openssl rand -hex 24)"
SETUP="$(python - <<'PY'
import json,os
print(json.dumps({'email':os.environ['CI_EMAIL'],'password':os.environ['CI_PASSWORD']}))
PY
)"
export SESSION="$(curl -fsS -X POST http://127.0.0.1:3001/api/auth/setup -H 'Content-Type: application/json' -d "$SETUP" | python -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
export FREELLMAPI_API_KEY="$(curl -fsS http://127.0.0.1:3001/api/settings/api-key -H "Authorization: Bearer $SESSION" | python -c 'import json,sys; print(json.load(sys.stdin)["apiKey"])')"
[[ "$FREELLMAPI_API_KEY" == freellmapi-* ]]
export MODELS="$(curl -fsS "$BASE/models" -H "Authorization: Bearer $FREELLMAPI_API_KEY")"
python - <<'PY'
import json,os
x=json.loads(os.environ['MODELS']); assert x.get('data'), 'no FreeLLMAPI models'
print(f'FREELLMAPI_MODELS=PASS count={len(x["data"])}')
PY
export SMOKE="$(curl -fsS "$BASE/chat/completions" -H "Authorization: Bearer $FREELLMAPI_API_KEY" -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Return exactly OK"}],"temperature":0,"max_tokens":8}')"
python - <<'PY'
import json,os
x=json.loads(os.environ['SMOKE']); text=(((x.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip(); assert text
print('FREELLMAPI_INFERENCE=PASS')
PY

{
 echo "FREELLMAPI_BASE_URL=$BASE"
 echo "FREELLMAPI_API_KEY=$FREELLMAPI_API_KEY"
 echo "FREELLMAPI_MODEL=auto"
 echo "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1"
 echo "OLLAMA_MODEL=$OLLAMA_MODEL"
} >> "$GITHUB_ENV"
echo 'FREE_LOCAL_PROVIDER_STACK=PASS'
