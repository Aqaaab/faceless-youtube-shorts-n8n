#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, urllib.request
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050')); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100')); SCENES=int(os.environ.get('LONG_TARGET_SCENES','20'))
RETRIES=max(3,int(os.environ.get('LONG_PROVIDER_SCHEMA_RETRIES','4')))
PROMPT=f'''Create ONE factual, high-retention YouTube long-form story in English. Return ONLY one JSON object, no markdown.
Create EXACTLY {SCENES} scenes and NEVER change the scene count during repair. Each scene MUST contain text_en, text_ar, visual_subject, pexels_query, and beat.
Each text_en scene MUST contain 45-70 English words; target 55-60. Total English narration MUST be {MIN_WORDS}-{MAX_WORDS} words.
text_en English only. text_ar faithful Modern Standard Arabic. visual_subject 2-5 concrete English words. pexels_query 3-7 concrete English words. Do not use empty fields.
Use every beat at least once: hook, setup, mystery, escalation, evidence, reveal, payoff, ending. Include topic, category, title <=90 chars, 3-5 sentence factual description, and 8-15 lowercase ASCII tags.
During repair, preserve all valid scenes and ONLY fix the reported validation error. Before returning, count scenes, words, languages, beats and metadata.'''

def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))

def normalize(d):
    for s in d.get('scenes',[]) if isinstance(d.get('scenes'),list) else []:
        vs=str(s.get('visual_subject','')).strip().split(); q=str(s.get('pexels_query','')).strip().split()
        if len(vs)>5: vs=vs[:5]
        while len(vs)<2: vs.append('scene')
        if len(q)>7: q=q[:7]
        while len(q)<3: q.append('documentary')
        s['visual_subject']=' '.join(vs); s['pexels_query']=' '.join(q)
    return d

def validate(d):
    scenes=d.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=SCENES: raise ValueError(f'long story scene count invalid: expected {SCENES}')
    total=0; beats=set()
    for i,s in enumerate(scenes,1):
        if not isinstance(s,dict): raise ValueError(f'scene {i} not object')
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all((en,ar,vs,q,beat)): raise ValueError(f'scene {i} missing required fields')
        n=wc(en)
        if not 45<=n<=70: raise ValueError(f'scene {i} word count {n} outside 45-70')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language contract failed')
        if not 2<=len(vs.split())<=5 or not 3<=len(q.split())<=7: raise ValueError(f'scene {i} visual/query length contract failed')
        if beat not in {'hook','setup','mystery','escalation','evidence','reveal','payoff','ending'}: raise ValueError(f'scene {i} invalid beat')
        total+=n; beats.add(beat)
    if not MIN_WORDS<=total<=MAX_WORDS: raise ValueError(f'total narration {total} outside {MIN_WORDS}-{MAX_WORDS}')
    if len(beats)<8: raise ValueError('missing story beats')
    title=str(d.get('title','')).strip(); tags=d.get('tags',[]); desc=str(d.get('description','')).strip()
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags')
    if any(not re.fullmatch(r'[a-z0-9_-]+',str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    if not 3<=len([x for x in re.split(r'(?<=[.!?])\s+',desc) if x.strip()])<=5: raise ValueError('invalid description')
    d['script']=' '.join(s['text_en'].strip() for s in scenes); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in scenes); d['scene_count']=SCENES; d['script_words']=total; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d

def mistral(prompt):
    key=os.getenv('MISTRAL_API_KEY','').strip()
    if not key: raise RuntimeError('Mistral API key missing')
    body={'model':os.getenv('MISTRAL_MODEL','mistral-small-latest'),'messages':[{'role':'system','content':'Return exactly one JSON object. No markdown.'},{'role':'user','content':prompt}],'temperature':0.15,'max_tokens':4500,'response_format':{'type':'json_object'}}
    req=urllib.request.Request('https://api.mistral.ai/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json','Accept':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=180) as r: payload=json.loads(r.read().decode('utf-8','replace'))
    content=((payload.get('choices') or [{}])[0].get('message') or {}).get('content','')
    if isinstance(content,list): content=''.join(str(x.get('text','')) if isinstance(x,dict) else str(x) for x in content)
    text=str(content); a,b=text.find('{'),text.rfind('}')
    if a<0 or b<=a: raise RuntimeError('Mistral returned no JSON object')
    return json.loads(text[a:b+1])

def main():
    from ai_router import build_long_story_router, Provider, _classify
    router=build_long_story_router(); providers=list(router.providers)
    if os.getenv('MISTRAL_API_KEY'): providers.insert(0,Provider('Mistral',['long_story'],0,True,mistral,model=os.getenv('MISTRAL_MODEL','mistral-small-latest')))
    if not providers: raise SystemExit('NO_LONG_STORY_AI_PROVIDERS')
    last=''
    for p in providers:
        for attempt in range(1,RETRIES+1):
            feedback=(f'\nPREVIOUS VALIDATION FAILURE: {last}\nFix ONLY this failure. Keep EXACTLY {SCENES} scenes.' if last else '')
            try:
                if not router._eligible(p): print(f'LONG_STORY_PROVIDER_SKIP provider={p.name} reason=cooldown'); break
                result=normalize(p.call(PROMPT+feedback)); d=validate(result)
                router._record(p,'PASS',0)
                d.update({'provider':p.name,'model':p.model,'router':'Aqaaab AI Router','router_task':'long_story','generation_attempt':attempt})
                (RUN_DIR/'job.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(f'LONG_STORY_ROUTER=PASS provider={p.name} scenes={SCENES} words={d["script_words"]} try={attempt}')
                return 0
            except Exception as e:
                last=str(e); kind=_classify(e); print(f'LONG_STORY_ROUTER provider={p.name} attempt={attempt} class={kind} failed: {e}')
                router._record(p,kind,0,str(e))
                if kind in {'AUTH','PAID_REQUIRED','ACCESS_OR_QUOTA','MODEL_NOT_FOUND','RATE_LIMIT','TRANSIENT','BAD_REQUEST','UNKNOWN'}: break
                time.sleep(min(3,attempt))
    raise SystemExit(f'LONG_STORY_ROUTER exhausted providers: {last}')
if __name__=='__main__': raise SystemExit(main())
