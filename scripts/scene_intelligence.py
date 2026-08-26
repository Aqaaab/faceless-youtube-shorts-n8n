#!/usr/bin/env python3
from __future__ import annotations
import json,re,hashlib,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))

def keywords(text):
    words=re.findall(r"[A-Za-z0-9']+",(text or '').lower())
    stop={'the','a','an','and','or','to','of','in','on','for','with','is','are','was','were','this','that','it','as','by'}
    freq={}
    for w in words:
        if len(w)>=4 and w not in stop: freq[w]=freq.get(w,0)+1
    return [w for w,_ in sorted(freq.items(),key=lambda x:(-x[1],x[0]))[:6]]

def main():
    story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    scenes=story.get('scenes') or []
    if not scenes: raise SystemExit('SCENE_INTELLIGENCE_INPUT_MISSING')
    out=[]; hashes=set()
    for s in scenes:
        n=int(s.get('scene_number') or s.get('id') or len(out)+1)
        text=str(s.get('narration') or s.get('voiceover') or s.get('text') or '')
        keys=keywords(text)
        query=' '.join(keys) or f'cinematic scene {n}'
        intent='establishing' if n<=2 else 'escalation' if n< len(scenes)-3 else 'payoff'
        h=hashlib.sha256(re.sub(r'\s+',' ',text.lower()).encode()).hexdigest()[:16]
        duplicate=h in hashes; hashes.add(h)
        out.append({'scene_number':n,'scene_intent':intent,'visual_subject':keys[0] if keys else 'cinematic','search_query':query,'narration_hash':h,'duplicate_narration':duplicate})
    payload={'stage':'scene_intelligence','scene_count':len(out),'scenes':out,'duplicate_scene_count':sum(x['duplicate_narration'] for x in out)}
    (RUN_DIR/'scene_intelligence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"SCENE_INTELLIGENCE=PASS scenes={len(out)} duplicates={payload['duplicate_scene_count']}")
    return 0
if __name__=='__main__': raise SystemExit(main())
