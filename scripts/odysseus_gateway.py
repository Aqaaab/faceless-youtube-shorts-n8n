from __future__ import annotations
import json, os, urllib.error, urllib.request
from typing import Any

def _url(base: str) -> str:
    b=base.rstrip('/')
    return b if b.endswith('/api/v1/chat') else b + '/api/v1/chat'

def call(message: str, *, session: str|None=None, model: str|None=None, base_url: str|None=None, api_key: str|None=None, timeout: int=180) -> dict[str, Any]:
    base=(base_url or os.getenv('ODYSSEUS_GATEWAY_BASE_URL','')).strip()
    key=(api_key or os.getenv('ODYSSEUS_GATEWAY_API_KEY','')).strip()
    if not base: raise RuntimeError('ODYSSEUS_GATEWAY_BASE_URL is not configured')
    if not key: raise RuntimeError('ODYSSEUS_GATEWAY_API_KEY is not configured')
    payload={'message': message}
    if session: payload['session']=session
    if model: payload['model']=model
    req=urllib.request.Request(_url(base), data=json.dumps(payload,ensure_ascii=False).encode(), headers={'Authorization':f'Bearer {key}','Content-Type':'application/json','Accept':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body=json.loads(r.read().decode('utf-8','replace'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Odysseus HTTP {e.code}: {e.read().decode("utf-8","replace")[:1000]}') from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f'Odysseus transport failure: {e}') from e
    if not isinstance(body,dict) or not body.get('response'):
        raise RuntimeError('Odysseus returned no response')
    return body

def extract_json(body: dict[str,Any]) -> dict[str,Any]:
    value=body.get('response')
    if isinstance(value,dict): return value
    if not isinstance(value,str): raise ValueError('Odysseus response is not text or object')
    text=value.strip().replace('\ufeff','')
    a,b=text.find('{'),text.rfind('}')
    if a<0 or b<=a: raise ValueError('No JSON object in Odysseus response')
    raw=text[a:b+1]
    try: obj=json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json
        obj=repair_json(raw,return_objects=True)
    if not isinstance(obj,dict): raise ValueError('Odysseus JSON is not an object')
    return obj
