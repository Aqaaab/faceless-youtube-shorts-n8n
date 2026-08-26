#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/daily-production')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'long_story.json'; COUNCIL=Path(os.environ.get('IDEA_COUNCIL_FILE',str(RUN_DIR/'idea_judged.json')))
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050')); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100'))
MIN_SCENES=int(os.environ.get('LONG_MIN_SCENES','18')); MAX_SCENES=int(os.environ.get('LONG_MAX_SCENES','30'))
TARGET_SCENES=min(MAX_SCENES,max(MIN_SCENES,int(os.environ.get('LONG_TARGET_SCENES','20'))))
MAX_PROVIDER_ATTEMPTS=int(os.environ.get('LONG_PROVIDER_ATTEMPTS','12'))
BEATS=('hook','setup','mystery','escalation','evidence','reveal','payoff','ending')

BASE_INSTRUCTIONS=f'''Create ONE independent factual or clearly framed true-story YouTube long-form story in English. Return ONLY one JSON object, no markdown. HARD CONTRACT: {MIN_SCENES}-{MAX_SCENES} distinct scene objects; target {TARGET_SCENES}. Each scene MUST contain text_en (45-70 English words), text_ar (faithful Arabic translation), visual_subject (2-5 concrete physical words), pexels_query (3-7 concrete words), beat (one of {", ".join(BEATS)}). Total English narration MUST be {MIN_WORDS}-{MAX_WORDS} words. Use all eight beat types at least once. Scene 1 is the hook. Include topic, category, title <=90 characters, description of 3-5 specific sentences, and 8-15 lowercase ASCII tags. No fabricated quotes, unsupported absolute claims, filler, or CTA. Preserve qualifiers. Before returning, count scenes and English words and repair the object until every limit passes.'''

REPAIR_INSTRUCTIONS=f'''Regenerate the COMPLETE story as one valid JSON object. Do not discuss the failure and do not return an outline. Required contract: {MIN_SCENES}-{MAX_SCENES} scenes, target {TARGET_SCENES}; every scene has text_en 45-70 words, text_ar, visual_subject 2-5 words, pexels_query 3-7 words, valid beat; total English narration {MIN_WORDS}-{MAX_WORDS} words; all eight beats used; title <=90 chars; description 3-5 sentences; 8-15 lowercase ASCII tags. No fabricated quotes, absolute claims, filler, or CTA. Validate counts before answering. JSON only.'''

def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))

def validate(d):
    if not isinstance(d,dict): raise ValueError('long story response is not an object')
    sc=d.get('scenes')
    if not isinstance(sc,list) or not MIN_SCENES<=len(sc)<=MAX_SCENES:
        raise ValueError(f'long story scene count invalid: got={len(sc) if isinstance(sc,list) else "non-list"}, expected={MIN_SCENES}-{MAX_SCENES}')
    words=0; beats=[]
    for i,s in enumerate(sc,1):
        if not isinstance(s,dict): raise ValueError(f'scene {i} is not an object')
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all((en,ar,vs,q,beat)): raise ValueError(f'scene {i} missing required fields')
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
    title=str(d.get('title','')).strip(); desc=str(d.get('description','')).strip(); tags=d.get('tags',[])
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not desc or not 3<=len([x for x in re.split(r'(?<=[.!?])\s+',desc) if x.strip()])<=5: raise ValueError('invalid description contract')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags contract')
    if any(not re.fullmatch(r'[a-z0-9_-]+',str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    d['script']=' '.join(s['text_en'].strip() for s in sc); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in sc)
    d['scene_count']=len(sc); d['script_words']=words; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d

def council_context():
    if not COUNCIL.exists(): raise SystemExit('IDEA_COUNCIL_REQUIRED_FOR_PATENT')
    d=json.loads(COUNCIL.read_text(encoding='utf-8')); w=d.get('winner')
    if not w or w.get('status') not in ('winner',None): raise SystemExit('INVALID_IDEA_COUNCIL_WINNER')
    return w

def bootstrap_local_providers():
    if os.getenv('ENABLE_LOCAL_FREE_STACK','false').lower()!='true':
        print('LOCAL_PROVIDER_BOOTSTRAP=SKIP optional local stack disabled'); return
    print('LOCAL_PROVIDER_BOOTSTRAP=SKIP local stack must be provisioned externally')

def _result_parts(result,model):
    if isinstance(result,tuple) and len(result)==2 and isinstance(result[0],dict): return result[0], result[1]
    return result,model

def generate():
    winner=council_context(); context=json.dumps({'topic':winner.get('topic'),'core_question':winner.get('core_question'),'hook':winner.get('hook'),'novel_angle':winner.get('novel_angle')},ensure_ascii=False)
    first_prompt=f'''Use this approved Idea Generation Council winner as the sole story concept. Do not copy its source pattern, title, wording, scenes or claims. Create an independent factual or clearly framed story.
Council winner: {context}

{BASE_INSTRUCTIONS}'''
    bootstrap_local_providers()
    from ai_router import build_long_story_router
    router=build_long_story_router()
    try:
        from compatible_provider_pool import extend_router
        router=extend_router(router)
    except Exception as e:
        print(f'COMPATIBLE_PROVIDER_POOL_INIT_SKIP reason={e}')
    if not getattr(router,'providers',None): raise SystemExit('NO_ELIGIBLE_LONG_STORY_PROVIDERS')
    excluded=set(); previous_error=''; schema_failures={}; attempts=0; last=None
    max_attempts=min(MAX_PROVIDER_ATTEMPTS,max(4,len(router.providers)*2))
    for attempt in range(1,max_attempts+1):
        attempts=attempt
        feedback=(f'\nThe previous attempt failed this exact production validation: {previous_error}\nReturn a complete replacement, not a patch.' if previous_error else '')
        prompt=(first_prompt if attempt==1 else REPAIR_INSTRUCTIONS)+feedback
        try:
            result, provider, model=router.route(prompt,exclude=excluded)
            result,model=_result_parts(result,model)
            doc=validate(result)
            doc.update({'provider':provider,'model':model,'generation_attempt':attempt,'router':'Aqaaab AI Router','router_task':'long_story','idea_council_winner':winner})
            OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'LONG_STORY_PASS provider={provider} model={model or "default"} scenes={doc["scene_count"]} words={doc["script_words"]} attempt={attempt}')
            return
        except Exception as e:
            last=e; previous_error=str(e); print(f'Aqaaab AI Router long-story attempt {attempt} failed: {e}')
            # Provider-specific schema failures are isolated. Do not send the repair back to the same provider.
            kind=str(e).lower(); is_schema=any(x in kind for x in ('scene count','word count','language contract','missing story beats','invalid long-form','invalid tags','visual/query length contract','required fields','invalid beat','schema_invalid','no json object','invalid json object'))
            # If router itself reported the provider in its ledger, identify likely failed providers from non-cooldown state.
            if is_schema:
                for p in getattr(router,'providers',[]):
                    state=router._entry(p.name)
                    if state.get('last_error') and str(state.get('last_error'))[-200:] in str(e)[-200:]:
                        schema_failures[p.name]=schema_failures.get(p.name,0)+1
                # In a validation failure the current route has already consumed a provider; exclude the provider with the most recent validation error.
                candidates=[p.name for p in getattr(router,'providers',[]) if p.name not in excluded]
                if candidates:
                    # Prefer a provider whose state was not just schema-invalid.
                    ranked=sorted(candidates,key=lambda n:(router._entry(n).get('status')=='SCHEMA_INVALID',router._entry(n).get('failures',0)))
                    excluded.add(ranked[0])
                    try: router.report_validation_failure(ranked[0],e)
                    except Exception: pass
            # For hard entitlement/auth/model failures the router already put the provider on cooldown; no extra action is needed.
            if len(excluded)>=len(getattr(router,'providers',[]))-1 and attempt<max_attempts:
                # Clear only the current-run exclusion once every provider has had a chance; persistent cooldowns still apply.
                excluded=set()
    raise SystemExit(f'All routed AI providers failed for long story after {attempts} attempts: {last}')

if __name__=='__main__': generate()
