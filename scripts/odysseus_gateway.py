from __future__ import annotations
import json, os, urllib.error, urllib.request
from typing import Any


def _url(base: str) -> str:
    b = base.rstrip('/')
    return b if b.endswith('/api/v1/chat') else b + '/api/v1/chat'


def _direct_url(base: str) -> str:
    b = base.rstrip('/')
    return b if b.endswith('/chat/completions') else b + '/v1/chat/completions'


def call(message: str, *, session: str|None=None, model: str|None=None, base_url: str|None=None, api_key: str|None=None, timeout: int=180) -> dict[str, Any]:
    base = (base_url or os.getenv('ODYSSEUS_GATEWAY_BASE_URL','')).strip()
    key = (api_key or os.getenv('ODYSSEUS_GATEWAY_API_KEY','')).strip()
    if not base or not key:
        raise RuntimeError('Odysseus gateway configuration is incomplete')
    payload = {'message': message}
    if session: payload['session'] = session
    if model: payload['model'] = model
    req = urllib.request.Request(_url(base), data=json.dumps(payload,ensure_ascii=False).encode(), headers={'Authorization':f'Bearer {key}','Content-Type':'application/json','Accept':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode('utf-8','replace'))
        if not isinstance(body, dict) or not body.get('response'):
            raise RuntimeError('Odysseus returned no response')
        return body
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8','replace')[:1000]
        # 503 from our gateway means it is alive but has no upstream provider.
        # Do not fail the whole YouTube production: use the provider already
        # configured in the YouTube repository when available.
        if e.code == 503 and os.getenv('YOUTUBE_LLM_BASE_URL') and os.getenv('YOUTUBE_LLM_API_KEY'):
            return _direct_call(message, model=model, timeout=timeout)
        raise RuntimeError(f'Odysseus HTTP {e.code}: {detail}') from e
    except (urllib.error.URLError, TimeoutError) as e:
        if os.getenv('YOUTUBE_LLM_BASE_URL') and os.getenv('YOUTUBE_LLM_API_KEY'):
            return _direct_call(message, model=model, timeout=timeout)
        raise RuntimeError(f'Odysseus transport failure: {e}') from e


def _direct_call(message: str, *, model: str|None, timeout: int) -> dict[str, Any]:
    base = os.getenv('YOUTUBE_LLM_BASE_URL','').strip()
    key = os.getenv('YOUTUBE_LLM_API_KEY','').strip()
    if not base or not key:
        raise RuntimeError('No YouTube direct LLM fallback is configured')
    payload = {'model': model or os.getenv('YOUTUBE_LLM_MODEL',''), 'messages': [{'role':'user','content':message}]}
    if not payload['model']:
        raise RuntimeError('YOUTUBE_LLM_MODEL is not configured')
    req = urllib.request.Request(_direct_url(base), data=json.dumps(payload,ensure_ascii=False).encode(), headers={'Authorization':f'Bearer {key}','Content-Type':'application/json','Accept':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode('utf-8','replace'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Direct YouTube LLM HTTP {e.code}: {e.read().decode("utf-8","replace")[:1000]}') from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f'Direct YouTube LLM transport failure: {e}') from e
    try:
        content = body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError('Direct YouTube LLM returned an unexpected response shape') from e
    return {'response': content, 'model': body.get('model', payload['model']), 'provider': 'YouTubeFallback'}


def extract_json(body: dict[str,Any]) -> dict[str,Any]:
    value = body.get('response')
    if isinstance(value,dict): return value
    if not isinstance(value,str): raise ValueError('Odysseus response is not text or object')
    text=value.strip().replace('\ufeff','')
    a,b=text.find('{'),text.rfind('}')
    if a<0 or b<=a: raise ValueError('No JSON object in LLM response')
    raw=text[a:b+1]
    try: obj=json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json
        obj=repair_json(raw,return_objects=True)
    if not isinstance(obj,dict): raise ValueError('LLM JSON is not an object')
    return obj
