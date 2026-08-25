#!/usr/bin/env python3
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/daily-production'))
RUN_DIR.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1').rstrip('/')
MODEL = os.environ.get('CEREBRAS_MODEL', 'gpt-oss-120b')
FREE_ONLY = os.environ.get('CEREBRAS_FREE_ONLY', 'true').lower() == 'true'
MAX_CALLS = int(os.environ.get('CEREBRAS_MAX_CALLS_PER_RUN', '5'))


def _request(method, url, key, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
        'Accept': 'application/json', 'User-Agent': 'faceless-youtube-shorts/1.0'
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def _state():
    p = RUN_DIR / 'cerebras_usage.json'
    used = 0
    if p.exists():
        try: used = int(json.loads(p.read_text()).get('calls', 0))
        except Exception: pass
    return p, used


def health_check(key):
    if not FREE_ONLY:
        raise RuntimeError('CEREBRAS_FREE_ONLY must remain true for production')
    if not key:
        raise RuntimeError('CEREBRAS_API_KEY missing')
    try:
        data = _request('GET', f'{BASE}/models', key, timeout=20)
        ids = {str(x.get('id')) for x in data.get('data', []) if isinstance(x, dict)}
        if ids and MODEL not in ids:
            raise RuntimeError(f'Cerebras model not listed: {MODEL}')
        print(f'CEREBRAS_HEALTH=PASS model={MODEL}')
        return True
    except Exception as e:
        print(f'CEREBRAS_HEALTH=FAIL reason={e}')
        return False


def generate(key, prompt):
    if not FREE_ONLY: raise RuntimeError('CEREBRAS_FREE_ONLY must remain true for production')
    if not key: raise RuntimeError('CEREBRAS_API_KEY missing')
    if not health_check(key): raise RuntimeError('Cerebras health check failed')
    path, used = _state()
    if used >= MAX_CALLS: raise RuntimeError(f'Cerebras local quota guard reached {used}/{MAX_CALLS}')
    body = {'model': MODEL, 'messages': [
        {'role':'system','content':'Return exactly one JSON object. No markdown.'},
        {'role':'user','content':prompt}], 'temperature':0.1, 'max_tokens':12000}
    try:
        result = _request('POST', f'{BASE}/chat/completions', key, body, timeout=180)
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8','replace')[:800]
        raise RuntimeError(f'HTTP {e.code}: {text}')
    path.write_text(json.dumps({'calls': used + 1, 'model': MODEL, 'free_only': True}, indent=2) + '\n')
    print(f'CEREBRAS_INFERENCE=PASS model={MODEL} calls={used+1}/{MAX_CALLS}')
    choices = result.get('choices') or []
    content = ((choices[0].get('message') or {}).get('content') if choices else '') or ''
    a,b=content.find('{'),content.rfind('}')
    if a<0 or b<=a: raise ValueError('Cerebras returned no JSON object')
    raw=content[a:b+1]
    try: return json.loads(raw)
    except Exception:
        from json_repair import repair_json
        obj=repair_json(raw, return_objects=True)
        if not isinstance(obj,dict): raise ValueError('invalid Cerebras JSON')
        return obj


def classify_provider_error(exc):
    msg=str(exc).lower()
    if any(x in msg for x in ('401','unauthorized','invalid api key')): return 'AUTH'
    if any(x in msg for x in ('403','accessdenied','quota')): return 'ACCESS_OR_QUOTA'
    if any(x in msg for x in ('404','model_not_found','model not found')): return 'MODEL_NOT_FOUND'
    if '429' in msg or 'rate limit' in msg or 'too many requests' in msg: return 'RATE_LIMIT'
    if any(x in msg for x in ('400','invalid request','schema')): return 'BAD_REQUEST'
    return 'TRANSIENT_OR_UNKNOWN'
