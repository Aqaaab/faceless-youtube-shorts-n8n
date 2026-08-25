#!/usr/bin/env python3
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/daily-production'))
RUN_DIR.mkdir(parents=True, exist_ok=True)
QWEN_BASE_URL = os.environ.get('QWENCLOUD_BASE_URL', 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1').rstrip('/')
QWEN_FREE_ONLY = os.environ.get('QWENCLOUD_FREE_ONLY', 'true').lower() == 'true'
QWEN_MAX_CALLS = int(os.environ.get('QWENCLOUD_MAX_CALLS_PER_RUN', '3'))
QWEN_MODELS = [x.strip() for x in os.environ.get(
    'QWENCLOUD_MODEL_CANDIDATES',
    'qwen3.6-flash,qwen3.5-flash,qwen3.6-plus,qwen3.5-plus,qwen3.7-flash,qwen3.7-plus'
).split(',') if x.strip()]


def _post(url, body, headers, retries=2):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={**headers, 'User-Agent': 'faceless-youtube-shorts/1.0', 'Accept': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            text = e.read().decode('utf-8', 'replace')[:800]
            last = RuntimeError(f'HTTP {e.code}: {text}')
            if e.code in {401, 403, 404}:
                raise last
            if e.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        if attempt < retries:
            time.sleep(min(12, 2 ** (attempt - 1)))
    raise last or RuntimeError('request failed')


def _extract(text):
    text = (text or '').strip().replace('\ufeff', '')
    a, b = text.find('{'), text.rfind('}')
    if a < 0 or b <= a:
        raise ValueError('no JSON object')
    raw = text[a:b + 1]
    try:
        obj = json.loads(raw)
    except Exception:
        from json_repair import repair_json
        obj = repair_json(raw, return_objects=True)
    if not isinstance(obj, dict):
        raise ValueError('invalid JSON object')
    return obj


def _quota_state():
    path = RUN_DIR / 'qwencloud_usage.json'
    used = 0
    if path.exists():
        try:
            used = int(json.loads(path.read_text()).get('calls', 0))
        except Exception:
            used = 0
    return path, used


def _mark_qwen_call(model, used):
    path, _ = _quota_state()
    path.write_text(json.dumps({'calls': used + 1, 'model': model, 'free_only': True}, indent=2) + '\n')


def _qwen_models(k):
    req = urllib.request.Request(
        f'{QWEN_BASE_URL}/models',
        headers={'Authorization': f'Bearer {k}', 'Accept': 'application/json', 'User-Agent': 'faceless-youtube-shorts/1.0'},
        method='GET'
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode('utf-8', 'replace'))
        ids = {str(x.get('id')) for x in data.get('data', []) if isinstance(x, dict) and x.get('id')}
        return ids
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8', 'replace')[:500]
        raise RuntimeError(f'QwenCloud model-list HTTP {e.code}: {text}')


def qwencloud_long_story(k, prompt):
    if not QWEN_FREE_ONLY:
        raise RuntimeError('QWENCLOUD_FREE_ONLY must remain true for production')
    if not k:
        raise RuntimeError('QWENCLOUD_API_KEY missing')
    path, used = _quota_state()
    if used >= QWEN_MAX_CALLS:
        raise RuntimeError(f'QwenCloud local quota guard reached {used}/{QWEN_MAX_CALLS}')

    listed = _qwen_models(k)
    # Free-only safety: only try explicitly allow-listed models that the account exposes.
    # Never fall back to an arbitrary /models entry because model availability != free entitlement.
    candidates = [m for m in QWEN_MODELS if not listed or m in listed]
    if not candidates:
        raise RuntimeError('QwenCloud has no configured free-only model candidates available in /models')

    errors = []
    for model in candidates:
        try:
            body = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'Return exactly one JSON object. No markdown.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 12000,
                'response_format': {'type': 'json_object'},
            }
            result = _post(f'{QWEN_BASE_URL}/chat/completions', body, {
                'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'
            }, retries=2)
            _mark_qwen_call(model, used)
            print(f'QWENCLOUD_INFERENCE=PASS model={model} calls={used + 1}/{QWEN_MAX_CALLS}')
            return _extract(((result.get('choices') or [{}])[0].get('message') or {}).get('content', '')), model
        except Exception as e:
            msg = str(e)
            errors.append(f'{model}: {msg}')
            print(f'QWENCLOUD_MODEL_SKIP model={model} reason={msg}')
            # Access/payment/quota failures are handled by the outer Aqaaab Router cooldown.
            continue
    raise RuntimeError('QwenCloud all free-only model candidates failed: ' + ' | '.join(errors[-6:]))


def classify_provider_error(exc):
    msg = str(exc).lower()
    if any(x in msg for x in ('401', 'unauthorized', 'invalid api key')):
        return 'AUTH'
    if any(x in msg for x in ('402', 'payment_required', 'payment required')):
        return 'PAID_REQUIRED'
    if any(x in msg for x in ('403', 'unpurchased', 'accessdenied', 'allocationquota.freetieronly')):
        return 'ACCESS_OR_QUOTA'
    if any(x in msg for x in ('404', 'model_not_found', 'model not found')):
        return 'MODEL_NOT_FOUND'
    if '429' in msg or 'rate limit' in msg or 'too many requests' in msg:
        return 'RATE_LIMIT'
    if any(x in msg for x in ('400', 'invalid request', 'scene count', 'schema')):
        return 'BAD_REQUEST'
    return 'TRANSIENT_OR_UNKNOWN'
