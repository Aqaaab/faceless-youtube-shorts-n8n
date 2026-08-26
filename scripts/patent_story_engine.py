#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/daily-production')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'long_story.json'; COUNCIL=Path(os.environ.get('IDEA_COUNCIL_FILE',str(RUN_DIR/'idea_judged.json')))
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050')); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100')); MIN_SCENES=int(os.environ.get('LONG_MIN_SCENES','18')); MAX_SCENES=int(os.environ.get('LONG_MAX_SCENES','30'))
TARGET_SCENES=min(MAX_SCENES,max(MIN_SCENES,int(os.environ.get('LONG_TARGET_SCENES','20'))))
BEATS=('hook','setup','mystery','escalation','evidence','reveal','payoff','ending')
PROMPT=f'''Create ONE independent factual or clearly framed true-story YouTube long-form story in English. Return ONLY one JSON object, no markdown. HARD CONTRACT: produce BETWEEN {MIN_SCENES} AND {MAX_SCENES} distinct scene objects. Target exactly {TARGET_SCENES} scenes whenever possible, but any count inside the range is valid. NEVER return fewer than {MIN_SCENES} scenes. Each scene must contain text_en (45-70 English words), text_ar (faithful Arabic translation), visual_subject (2-5 concrete physical words), pexels_query (3-7 concrete words), and beat (hook/setup/mystery/escalation/evidence/reveal/payoff/ending). Total English narration must be {MIN_WORDS}-{MAX_WORDS} words. Use all eight beat types at least once. Structure: strong hook in scene 1, concise setup, central mystery/question, escalating discoveries, evidence, reveal/payoff, concise ending. No fabricated quotes, no unsupported absolute claims, no filler, no CTA. Include topic, category, title <=90 characters, description of 3-5 specific sentences, and 8-15 lowercase ASCII tags. Prefer 55-60 words per scene. Before returning, count the scenes and English words and repair the object if either value is outside the hard limits.'''
REPAIR=f'''REPAIR THE PREVIOUS RESPONSE. Return ONLY one JSON object. The previous output failed a production contract. DO NOT discuss the failure. Regenerate the COMPLETE long-form story, not a shortened outline. Produce BETWEEN {MIN_SCENES} AND {MAX_SCENES} distinct scene objects; target exactly {TARGET_SCENES} scenes. NEVER return fewer than {MIN_SCENES} scenes. Each scene MUST have 45-70 English words, Arabic translation, visual_subject, pexels_query and one of hook/setup/mystery/escalation/evidence/reveal/payoff/ending. Total English narration MUST be {MIN_WORDS}-{MAX_WORDS} words. Use all eight beats at least once. Preserve factuality and qualifiers. Do not fabricate quotes, add absolute claims, filler, or CTA. Title <=90 chars; description 3-5 specific sentences; tags 8-15 lowercase ASCII. Before returning, count scenes and English words and repair the complete object until it satisfies every limit. Return valid JSON only.'''

def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))

def validate(d):
    if not isinstance(d,dict): raise ValueError('long story response is not an object')
    sc=d.get('scenes')
    if not isinstance(sc,list) or not MIN_SCENES<=len(sc)<=MAX_SCENES: raise ValueError(f'long story scene count invalid: got={len(sc) if isinstance(sc,list) else "non-list"}, expected={MIN_SCENES}-{MAX_SCENES}')
    words=0; beats=[]
    for i,s in enumerate(sc,1):
        if not isinstance(s,dict): raise ValueError(f'scene {i} is not an object')
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all([en,ar,vs,q,beat]): raise ValueError(f'scene {i} missing required fields')
        n=wc(en)
        if not 45<=n<=70: raise ValueError(f'scene {i} word count {n} outside 45-70')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language contract failed')
        if re.search(r'\b(always|never|the only|100%)\b',en,re.I) or re.search(r'(دائماً|دائمًا|أبداً|أبدًا|للأبد|100٪)',ar): raise ValueError(f'scene {i} unsupported absolute claim')
        if not 2<=len(vs.split())<=5 or not 3<=len(q.split())<=7: raise ValueError(f'scene {i} visual/query length contract failed')
        if beat not in BEATS: raise ValueError(f'scene {i} invalid beat: {beat}')
        words+=n; beats.append(beat)
    if not MIN_WORDS<=words<=MAX_WORDS: raise ValueError(f'long narration words {words} outside {MIN_WORDS}-{MAX_WORDS}')
    missing=[b for b in BEATS if b not in beats]
    if missing: raise ValueError('missing story beats: '+','.join(missing))
    title=str(d.get('title','')).strip(); tags=d.get('tags',[]); desc=str(d.get('description','')).strip()
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not desc or not 3<=len([x for x in re.split(r'(?<=[.!?])\s+',desc) if x.strip()])<=5: raise ValueError('invalid description contract')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags contract')
    if any(not re.fullmatch(r'[a-z0-9_-]+',str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    d['script']=' '.join(s['text_en'].strip() for s in sc); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in sc); d['scene_count']=len(sc); d['script_words']=words; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d

def council_context():
    if not COUNCIL.exists(): raise SystemExit('IDEA_COUNCIL_REQUIRED_FOR_PATENT')
    d=json.loads(COUNCIL.read_text(encoding='utf-8')); w=d.get('winner')
    if not w or w.get('status') not in ('winner',None): raise SystemExit('INVALID_IDEA_COUNCIL_WINNER')
    return w

def bootstrap_local_providers():
    script=Path(__file__).with_name('bootstrap_local_free_providers.sh')
    if not script.exists():
        raise SystemExit('LOCAL_PROVIDER_BOOTSTRAP_MISSING')
    env=os.environ.copy()
    env.setdefault('OLLAMA_MODEL','qwen3:8b')
    env.setdefault('OLLAMA_BASE_URL','http://127.0.0.1:11434/v1')
    subprocess.run(['bash',str(script)],check=True,env=env)

def generate():
    winner=council_context(); context=json.dumps({'topic':winner.get('topic'),'core_question':winner.get('core_question'),'hook':winner.get('hook'),'novel_angle':winner.get('novel_angle')},ensure_ascii=False)
    council_prompt=f'''Use this approved Idea Generation Council winner as the sole story concept. Do not copy its source pattern, title, wording, scenes or claims. Create an independent factual or clearly framed true-story story from the approved concept. Council winner: {context}\n\n{PROMPT}'''
    bootstrap_local_providers()
    from ai_router import build_long_story_router
    router=build_long_story_router()
    try:
        from compatible_provider_pool import extend_router
        router=extend_router(router)
    except Exception as e: print(f'COMPATIBLE_PROVIDER_POOL_INIT_SKIP reason={e}')
    last=None; excluded=set(); previous_error=''; validation_failures={}
    attempts=max(6,min(12,len(router.providers)*2 if hasattr(router,'providers') else 6))
    for attempt in range(1,attempts+1):
        provider=None
        feedback=f'\nPrevious validation failure: {previous_error}. Fix that exact contract failure.' if previous_error else ''
        prompt=(council_prompt if attempt==1 else REPAIR)+feedback
        try:
            result, provider, model = router.route(prompt, exclude=excluded)
            if isinstance(result, tuple) and len(result)==2 and isinstance(result[1],str): result, model=result
            d=validate(result); d['provider']=provider; d['model']=model; d['generation_attempt']=attempt; d['router']='Aqaaab AI Router'; d['router_task']='long_story'; d['idea_council_winner']=winner
            OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'LONG_STORY router=Aqaaab-AI-Router provider={provider} model={d.get("model") or "default"} council_winner={winner["idea_id"]} scenes={d["scene_count"]} words={d["script_words"]} attempt={attempt}')
            return
        except Exception as e:
            last=e; previous_error=str(e); print(f'Aqaaab AI Router long-story attempt {attempt} failed: {e}')
            msg=str(e).lower(); is_schema=any(x in msg for x in ('scene count','word count','language contract','missing story beats','invalid long-form','invalid tags','schema_invalid','schema invalid','visual/query length contract','required fields','invalid beat'))
            if provider and is_schema:
                provider_names={p.name for p in getattr(router,'providers',[])}
                only_this=provider_names-{provider}
                repair_prompt=REPAIR+f'''\nThe last response from provider {provider} failed this exact validation: {previous_error}\nReturn a COMPLETE replacement JSON object. Do not shorten the story. Count scenes and English words before responding.'''
                for repair_idx in range(1,3):
                    try:
                        repaired_result, repaired_provider, repaired_model = router.route(repair_prompt, exclude=only_this)
                        repaired_doc=validate(repaired_result)
                        repaired_doc['provider']=repaired_provider; repaired_doc['model']=repaired_model; repaired_doc['generation_attempt']=attempt; repaired_doc['repair_attempt']=repair_idx; repaired_doc['router']='Aqaaab AI Router'; repaired_doc['router_task']='long_story'; repaired_doc['idea_council_winner']=winner
                        OUT.write_text(json.dumps(repaired_doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                        print(f'LONG_STORY_REPAIR_PASS provider={repaired_provider} scenes={repaired_doc["scene_count"]} words={repaired_doc["script_words"]} repair_attempt={repair_idx}')
                        return
                    except Exception as repair_error:
                        last=repair_error; previous_error=str(repair_error); print(f'LONG_STORY_REPAIR_FAIL provider={provider} attempt={repair_idx}: {repair_error}')
                validation_failures[provider]=validation_failures.get(provider,0)+1
                if validation_failures[provider] >= 2:
                    try: router.report_validation_failure(provider,e)
                    except Exception: pass
                    excluded.add(provider)
                continue
            if provider: excluded.add(provider)
    raise SystemExit(f'All routed AI providers failed for long story: {last}')

if __name__=='__main__': generate()
