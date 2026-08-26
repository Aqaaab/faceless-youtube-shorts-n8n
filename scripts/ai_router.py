from __future__ import annotations
import json, os, urllib.request
from provider_registry import enabled
from odysseus_gateway import extract_json

def call_fallback(message:str, *, task:str='long_story'):
    errors=[]
    for p in enabled(task):
        base=os.environ[p['base_url_env']].rstrip('/')
        url=base+'/chat/completions'
        payload={'model':os.environ[p['model_env']],'messages':[{'role':'user','content':message}],'temperature':0.7}
        req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ[p['api_key_env']],'Content-Type':'application/json','Accept':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=120) as r: body=json.loads(r.read().decode('utf-8','replace'))
            text=body['choices'][0]['message']['content']
            return extract_json({'response':text}), p['id']
        except Exception as exc:
            errors.append(f"{p['id']}:{exc}")
    raise RuntimeError('No eligible fallback provider succeeded; '+' | '.join(errors))
