#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/daily-production')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'long_story.json'; SLOTS_FILE=Path(os.environ.get('LONG_STORY_SLOTS_CONFIG','config/long-story-slots.json'))
COUNCIL=Path(os.environ.get('IDEA_COUNCIL_FILE',str(RUN_DIR/'idea_judged.json')))
CFG=json.loads(SLOTS_FILE.read_text(encoding='utf-8'))
SCENE_CFG=CFG['scene_contract']; SLOTS=CFG['slots']; RULES=CFG['rules']
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS',SCENE_CFG['total_min_words'])); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS',SCENE_CFG['total_max_words']))
MIN_SCENES=int(os.environ.get('LONG_MIN_SCENES',SCENE_CFG['min_scenes'])); MAX_SCENES=int(os.environ.get('LONG_MAX_SCENES',SCENE_CFG['max_scenes']))
MAX_COOLDOWN_WAIT=int(os.environ.get('LONG_MAX_COOLDOWN_WAIT','180'))
BEATS=('hook','setup','mystery','escalation','evidence','reveal','payoff','ending')


def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))

def _words_ok(n, lo=45, hi=70): return lo <= n <= hi

def validate_scene(scene,index):
    if not isinstance(scene,dict): raise ValueError(f'scene {index} is not an object')
    en=str(scene.get('text_en','')).strip(); ar=str(scene.get('text_ar','')).strip(); vs=str(scene.get('visual_subject','')).strip(); q=str(scene.get('pexels_query','')).strip(); beat=str(scene.get('beat','')).strip().lower()
    if not all((en,ar,vs,q,beat)): raise ValueError(f'scene {index} missing required fields')
    n=wc(en)
    if not _words_ok(n): raise ValueError(f'scene {index} word count {n} outside 45-70')
    if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {index} language contract failed')
    if re.search(r'\b(always|never|the only|100%)\b',en,re.I) or re.search(r'(دائماً|دائمًا|أبداً|أبدًا|للأبد|100٪)',ar): raise ValueError(f'scene {index} unsupported absolute claim')
    if not 2<=len(vs.split())<=5 or not 3<=len(q.split())<=7: raise ValueError(f'scene {index} visual/query length contract failed')
    if beat not in BEATS: raise ValueError(f'scene {index} invalid beat: {beat}')
    return n

def validate_slot(doc,slot):
    if not isinstance(doc,dict): raise ValueError(f'{slot["slot_id"]} response is not an object')
    scenes=doc.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=slot['scene_count']:
        got=len(scenes) if isinstance(scenes,list) else 'non-list'
        raise ValueError(f'{slot["slot_id"]} scene count invalid: got={got}, expected={slot["scene_count"]}')
    total=0; beats=[]
    for offset,scene in enumerate(scenes):
        number=slot['start_scene']+offset; total+=validate_scene(scene,number); beats.append(str(scene.get('beat')).lower())
    if not slot['min_words']<=total<=slot['max_words']:
        raise ValueError(f'{slot["slot_id"]} words {total} outside {slot["min_words"]}-{slot["max_words"]}')
    missing=[b for b in slot['required_beats'] if b not in beats]
    if missing: raise ValueError(f'{slot["slot_id"]} missing required beats: {",".join(missing)}')
    return scenes,total

def validate_final(d):
    if not isinstance(d,dict): raise ValueError('long story response is not an object')
    scenes=d.get('scenes')
    if not isinstance(scenes,list) or not MIN_SCENES<=len(scenes)<=MAX_SCENES: raise ValueError(f'long story scene count invalid: got={len(scenes) if isinstance(scenes,list) else "non-list"}, expected={MIN_SCENES}-{MAX_SCENES}')
    words=0; beats=[]; expected=1
    for i,scene in enumerate(scenes,1):
        if int(scene.get('scene_number',i))!=expected: raise ValueError(f'scene numbering gap at {i}')
        scene['scene_number']=i; words+=validate_scene(scene,i); beats.append(str(scene.get('beat')).lower()); expected+=1
    if not MIN_WORDS<=words<=MAX_WORDS: raise ValueError(f'long narration words {words} outside {MIN_WORDS}-{MAX_WORDS}')
    missing=[b for b in BEATS if b not in beats]
    if missing: raise ValueError('missing story beats: '+','.join(missing))
    title=str(d.get('title','')).strip(); desc=str(d.get('description','')).strip(); tags=d.get('tags',[])
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not desc or not 3<=len([x for x in re.split(r'(?<=[.!?])\s+',desc) if x.strip()])<=5: raise ValueError('invalid description contract')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags contract')
    if any(not re.fullmatch(r'[a-z0-9_-]+',str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    d['script']=' '.join(s['text_en'].strip() for s in scenes); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in scenes); d['scene_count']=len(scenes); d['script_words']=words; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d

def council_context():
    if not COUNCIL.exists(): raise SystemExit('IDEA_COUNCIL_REQUIRED_FOR_PATENT')
    d=json.loads(COUNCIL.read_text(encoding='utf-8')); w=d.get('winner')
    if not w or w.get('status') not in ('winner',None): raise SystemExit('INVALID_IDEA_COUNCIL_WINNER')
    return w

def bootstrap_local_providers():
    if os.getenv('ENABLE_LOCAL_FREE_STACK','false').lower()!='true': print('LOCAL_PROVIDER_BOOTSTRAP=SKIP optional local stack disabled'); return
    print('LOCAL_PROVIDER_BOOTSTRAP=SKIP local stack must be provisioned externally')

def _is_schema_error(msg):
    return any(x in str(msg).lower() for x in ('scene count','word count','language contract','missing required beats','missing story beats','invalid long-form','invalid tags','visual/query length contract','required fields','invalid beat','schema_invalid','no json object','invalid json object'))

def _wait_for_ready(router,exclude):
    delay=router.next_ready_delay(exclude=exclude)
    if delay is None: return False
    delay=max(1,min(int(delay),60))
    if delay>MAX_COOLDOWN_WAIT: return False
    print(f'LONG_STORY_WAIT_FOR_PROVIDER_COOLDOWN delay={delay}s'); time.sleep(delay); router.clear_expired_cooldowns(); return True

def _slot_prompt(base_context,slot,prior_tail,repair_error=''):
    prior=json.dumps(prior_tail,ensure_ascii=False) if prior_tail else '[]'
    beats=', '.join(slot['required_beats'])
    repair=f'\nPrevious validation failure for this SAME slot: {repair_error}\nFix only this slot and return a complete replacement for scenes {slot["start_scene"]}-{slot["end_scene"]}.' if repair_error else ''
    return f'''Create ONLY slot {slot["slot_id"]} of one independent factual or clearly framed true-story YouTube video. This slot owns EXACTLY scenes {slot["start_scene"]}-{slot["end_scene"]} ({slot["scene_count"]} scenes). NEVER change the scene range, skip scenes, or generate another slot.\n\nApproved story context: {base_context}\nPrevious slot ending scenes (continuity reference only): {prior}\nSlot purpose: {slot["purpose"]}. Required beats in this slot: {beats}.\n\nReturn ONLY one JSON object with this shape: {{"slot_id":"{slot["slot_id"]}","scenes":[{{"scene_number":{slot["start_scene"]},"text_en":"...","text_ar":"...","visual_subject":"...","pexels_query":"...","beat":"..."}}]}}\nHard contract: exactly {slot["scene_count"]} scenes; each text_en 45-70 English words; text_ar is Arabic; visual_subject 2-5 concrete words; pexels_query 3-7 concrete words; beats limited to {", ".join(BEATS)}; slot English word total {slot["min_words"]}-{slot["max_words"]}; JSON only; no fabricated quotes, unsupported absolute claims, filler, or CTA. Scene numbering MUST be consecutive from {slot["start_scene"]} to {slot["end_scene"]}. Do not write title, description, tags, or any scenes outside this slot.{repair}'''

def generate():
    winner=council_context(); base_context=json.dumps({'topic':winner.get('topic'),'core_question':winner.get('core_question'),'hook':winner.get('hook'),'novel_angle':winner.get('novel_angle')},ensure_ascii=False)
    bootstrap_local_providers()
    from ai_router import build_long_story_router
    router=build_long_story_router()
    try:
        from compatible_provider_pool import extend_router
        router=extend_router(router)
    except Exception as e: print(f'COMPATIBLE_PROVIDER_POOL_INIT_SKIP reason={e}')
    if not getattr(router,'providers',None): raise SystemExit('NO_ELIGIBLE_LONG_STORY_PROVIDERS')
    all_scenes=[]; slot_results=[]; prior_tail=[]
    for slot in SLOTS:
        excluded=set(); slot_error=''; completed=False; attempt=0; last=None
        max_attempts=max(4,min(int(os.environ.get('LONG_SLOT_ATTEMPTS','8')),len(router.providers)*2))
        while attempt<max_attempts and not completed:
            attempt+=1; router.clear_expired_cooldowns()
            try:
                prompt=_slot_prompt(base_context,slot,prior_tail,slot_error)
                result,provider,model=router.route(prompt,exclude=excluded,wait_for_ready=True,max_wait_seconds=MAX_COOLDOWN_WAIT)
                if isinstance(result,tuple) and len(result)==2 and isinstance(result[0],dict): result,model=result
                scenes,words=validate_slot(result,slot)
                for offset,scene in enumerate(scenes): scene['scene_number']=slot['start_scene']+offset; scene['slot_id']=slot['slot_id']; scene['provider']=provider
                all_scenes.extend(scenes); slot_results.append({'slot_id':slot['slot_id'],'start_scene':slot['start_scene'],'end_scene':slot['end_scene'],'provider':provider,'model':model,'attempt':attempt,'words':words,'status':'PASS'})
                prior_tail=scenes[-2:]; completed=True
                print(f'LONG_STORY_SLOT_PASS slot={slot["slot_id"]} scenes={slot["start_scene"]}-{slot["end_scene"]} provider={provider} attempt={attempt}')
            except Exception as e:
                last=e; slot_error=str(e); print(f'LONG_STORY_SLOT_FAIL slot={slot["slot_id"]} attempt={attempt}: {e}')
                if 'provider' in locals() and provider:
                    excluded.add(provider)
                    try: router.report_validation_failure(provider,e)
                    except Exception: pass
                    print(f'LONG_STORY_SLOT_PROVIDER_QUARANTINE slot={slot["slot_id"]} provider={provider}')
                if len(excluded)>=len(router.providers):
                    excluded.clear();
                    if not _wait_for_ready(router,excluded): break
        if not completed:
            raise SystemExit(f'LONG_STORY_SLOT_ABORT slot={slot["slot_id"]} failed without advancing to next slot: {last}')
    if len(all_scenes)!=sum(int(s['scene_count']) for s in SLOTS): raise SystemExit('LONG_STORY_SLOT_MERGE_COUNT_MISMATCH')
    merged={'title':winner.get('title') or winner.get('topic') or 'Untold Mystery','description':winner.get('description') or 'An original research-driven story built from the approved idea.','tags':winner.get('tags') or ['mystery','history','discovery','unknown','story','explained','facts','research'], 'topic':winner.get('topic'),'category':'Stories','scenes':all_scenes,'slot_results':slot_results,'router':'Aqaaab AI Router','router_task':'long_story_slots','idea_council_winner':winner}
    validate_final(merged)
    OUT.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'LONG_STORY_PASS mode=fixed_slots slots={len(SLOTS)} scenes={merged["scene_count"]} words={merged["script_words"]}')

if __name__=='__main__': generate()
