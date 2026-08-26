#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050')); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100'))
SCENES=int(os.environ.get('LONG_TARGET_SCENES','20')); CHUNK_SIZE=5
RETRIES=max(3,int(os.environ.get('LONG_PROVIDER_SCHEMA_RETRIES','4')))

BASE_PROMPT=f'''Create one factual, high-retention YouTube long-form story in English. Return ONLY one JSON object, no markdown.
This request is one chunk of a larger story. The FINAL story has EXACTLY {SCENES} scenes. For this chunk create EXACTLY {CHUNK_SIZE} consecutive scenes.
Each scene MUST contain text_en, text_ar, visual_subject, pexels_query, and beat.
Each text_en MUST contain 45-70 English words; TARGET 53-56 words. Do not go below 45. Keep the chunk near 265-280 English words.
text_en English only. text_ar faithful Modern Standard Arabic with roughly the same meaning. visual_subject 2-5 concrete English words. pexels_query 3-7 concrete English words. beat must be one of hook, setup, mystery, escalation, evidence, reveal, payoff, ending.
Never omit a scene, never return fewer or more than {CHUNK_SIZE} scenes, and never merge scenes. Return complete JSON, not a partial/truncated response.'''


def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))


def normalize_scene(s):
    s=dict(s)
    vs=str(s.get('visual_subject','')).strip().split(); q=str(s.get('pexels_query','')).strip().split()
    s['visual_subject']=' '.join(vs[:5] if len(vs)>=2 else vs+['scene']*(2-len(vs)))
    s['pexels_query']=' '.join(q[:7] if len(q)>=3 else q+['documentary']*(3-len(q)))
    return s


def validate_chunk(d, start_scene):
    scenes=d.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=CHUNK_SIZE:
        raise ValueError(f'chunk scene count invalid: expected {CHUNK_SIZE}, received {len(scenes) if isinstance(scenes,list) else "non-list"}')
    out=[]
    for offset,raw in enumerate(scenes):
        i=start_scene+offset; s=normalize_scene(raw)
        if not isinstance(s,dict): raise ValueError(f'scene {i} not object')
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all((en,ar,s.get('visual_subject'),s.get('pexels_query'),beat)): raise ValueError(f'scene {i} missing required fields')
        n=wc(en)
        if not 45<=n<=70: raise ValueError(f'scene {i} word count {n} outside 45-70')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language contract failed')
        if not 2<=len(s['visual_subject'].split())<=5 or not 3<=len(s['pexels_query'].split())<=7: raise ValueError(f'scene {i} visual/query length contract failed')
        if beat not in {'hook','setup','mystery','escalation','evidence','reveal','payoff','ending'}: raise ValueError(f'scene {i} invalid beat')
        out.append(s)
    return out


def validate_final(d):
    scenes=d.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=SCENES: raise ValueError(f'long story scene count invalid: expected {SCENES}')
    total=sum(wc(s['text_en']) for s in scenes)
    if not MIN_WORDS<=total<=MAX_WORDS: raise ValueError(f'total narration {total} outside {MIN_WORDS}-{MAX_WORDS}')
    beats={str(s['beat']).lower() for s in scenes}
    if len(beats)<8: raise ValueError('missing story beats')
    title=str(d.get('title','')).strip(); desc=str(d.get('description','')).strip(); tags=d.get('tags',[])
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags')
    if any(not re.fullmatch(r'[a-z0-9_-]+',str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    if not 3<=len([x for x in re.split(r'(?<=[.!?])\s+',desc) if x.strip()])<=5: raise ValueError('invalid description')
    d['script']=' '.join(s['text_en'].strip() for s in scenes); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in scenes)
    d['scene_count']=SCENES; d['script_words']=total; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d


def main():
    from ai_router import build_long_story_router, Provider
    from router_long_story import __dict__ as _self
    router=build_long_story_router(); providers=list(router.providers)
    if not providers: raise SystemExit('NO_LONG_STORY_AI_PROVIDERS')
    for p in providers:
        if not router._eligible(p):
            print(f'LONG_STORY_PROVIDER_SKIP provider={p.name} reason=cooldown'); continue
        all_scenes=[]; meta={}; failed=False
        for chunk_index in range(4):
            start=chunk_index*CHUNK_SIZE+1; end=start+CHUNK_SIZE-1
            prompt=BASE_PROMPT+f'''\nGenerate scenes {start}-{end} now. These scenes must flow naturally from the previous chunk when applicable.\n'''
            if chunk_index==0:
                prompt+='''Also include topic, category, title (<=90 chars), description (3-5 factual sentences), and 8-15 lowercase ASCII tags.\n'''
            else:
                prompt+='''Do NOT include or regenerate title, description, tags, topic, or category; only return the scenes array.\n'''
            last=''
            for attempt in range(1,RETRIES+1):
                try:
                    result=p.call(prompt+(f'\nPREVIOUS VALIDATION FAILURE: {last}\nFix ONLY that failure. Keep EXACTLY {CHUNK_SIZE} scenes.' if last else ''))
                    scenes=validate_chunk(result,start)
                    all_scenes.extend(scenes)
                    if chunk_index==0:
                        meta={k:result.get(k) for k in ('topic','category','title','description','tags')}
                    print(f'LONG_STORY_CHUNK=PASS provider={p.name} scenes={start}-{end} try={attempt}')
                    break
                except Exception as e:
                    last=str(e); print(f'LONG_STORY_ROUTER provider={p.name} chunk={start}-{end} attempt={attempt} failed: {e}')
                    if attempt<RETRIES: time.sleep(min(3,attempt))
            else:
                failed=True; break
        if failed: continue
        try:
            final=validate_final({**meta,'scenes':all_scenes})
            final.update({'provider':p.name,'model':p.model,'router':'Aqaaab AI Router','router_task':'long_story','generation_attempt':1})
            (RUN_DIR/'job.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'LONG_STORY_ROUTER=PASS provider={p.name} scenes={SCENES} words={final["script_words"]}')
            return 0
        except Exception as e:
            print(f'LONG_STORY_ROUTER provider={p.name} final_validation failed: {e}')
            continue
    raise SystemExit('LONG_STORY_ROUTER exhausted providers/chunk generation attempts')

if __name__=='__main__': raise SystemExit(main())
