#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/daily-production')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'long_story.json'; COUNCIL=Path(os.environ.get('IDEA_COUNCIL_FILE',str(RUN_DIR/'idea_judged.json')))
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050')); MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100')); MIN_SCENES=int(os.environ.get('LONG_MIN_SCENES','18')); MAX_SCENES=int(os.environ.get('LONG_MAX_SCENES','30'))
PROMPT=f'''Create one factual or clearly framed true-story YouTube long-form story in English. Target 7-15 minutes. Return ONLY JSON. Use {MIN_SCENES}-{MAX_SCENES} scenes. Each scene must contain text_en (35-80 words), text_ar (faithful Arabic translation), visual_subject (2-5 concrete physical words), pexels_query (3-7 concrete words), and beat (hook/setup/mystery/escalation/evidence/reveal/payoff/ending). The complete narration must be {MIN_WORDS}-{MAX_WORDS} English words. Structure: Hook in the first scene, setup, central mystery/question, escalating discoveries, evidence, reveal/payoff, concise ending. No fabricated quotes, no absolute claims, no filler, no CTA. Include topic, category, title <=90 characters, description of 3-5 specific sentences, and 8-15 lowercase ASCII tags.'''
REPAIR=f'''Repair the previous long-form story response. Return ONLY one JSON object, no markdown. Produce {MIN_SCENES}-{MAX_SCENES} scenes and {MIN_WORDS}-{MAX_WORDS} total English words. Every scene needs text_en (35-80 words), text_ar, visual_subject, pexels_query and beat. Include all eight beats: hook, setup, mystery, escalation, evidence, reveal, payoff, ending. Title <=90 chars; description 3-5 specific sentences; tags 8-15 lowercase ASCII. Do not fabricate quotes or use absolute claims.'''
def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))
def validate(d):
    sc=d.get('scenes')
    if not isinstance(sc,list) or not MIN_SCENES<=len(sc)<=MAX_SCENES: raise ValueError('long story scene count invalid')
    words=0; beats=[]
    for i,s in enumerate(sc,1):
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all([en,ar,vs,q,beat]): raise ValueError(f'scene {i} missing required fields')
        n=wc(en)
        if not 35<=n<=80: raise ValueError(f'scene {i} word count {n} outside 35-80')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language contract failed')
        if re.search(r'\b(always|never|the only|100%)\b',en,re.I) or re.search(r'(دائماً|دائمًا|أبداً|أبدًا|للأبد|100٪)',ar): raise ValueError(f'scene {i} unsupported absolute claim')
        words+=n; beats.append(beat)
    if not MIN_WORDS<=words<=MAX_WORDS: raise ValueError(f'long narration words {words} outside {MIN_WORDS}-{MAX_WORDS}')
    missing=[b for b in ('hook','setup','mystery','escalation','evidence','reveal','payoff','ending') if b not in beats]
    if missing: raise ValueError('missing story beats: '+','.join(missing))
    title=str(d.get('title','')).strip(); tags=d.get('tags',[])
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    if not isinstance(tags,list) or not 8<=len(tags)<=15: raise ValueError('invalid tags contract')
    d['script']=' '.join(s['text_en'].strip() for s in sc); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in sc); d['scene_count']=len(sc); d['script_words']=words; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d
def council_context():
    if not COUNCIL.exists(): raise SystemExit('IDEA_COUNCIL_REQUIRED_FOR_PATENT')
    d=json.loads(COUNCIL.read_text(encoding='utf-8')); w=d.get('winner')
    if not w or w.get('status') not in ('winner',None): raise SystemExit('INVALID_IDEA_COUNCIL_WINNER')
    return w
def generate():
    winner=council_context(); context=json.dumps({'topic':winner.get('topic'),'core_question':winner.get('core_question'),'hook':winner.get('hook'),'novel_angle':winner.get('novel_angle'),'source_pattern':winner.get('source_pattern')},ensure_ascii=False)
    council_prompt=f'''Use this approved Idea Generation Council winner as the sole story concept. Do not copy its source pattern, title, wording, scenes or claims. Create an independent factual or clearly framed true-story story from the approved concept. Council winner: {context}\n\n{PROMPT}'''
    from generate_job import openrouter,gemini,cf,compat
    from patent_provider_router import qwencloud_long_story, classify_provider_error
    from cerebras_provider import generate as cerebras_generate
    providers=[]
    if os.getenv('OPENROUTER_API_KEY'): providers.append(('OpenRouter',lambda p:openrouter(os.environ['OPENROUTER_API_KEY'],p)))
    if os.getenv('GEMINI_API_KEY'): providers.append(('Gemini',lambda p:gemini(os.environ['GEMINI_API_KEY'],p)))
    if os.getenv('CLOUDFLARE_API_TOKEN') and os.getenv('CLOUDFLARE_ACCOUNT_ID'): providers.append(('Cloudflare',lambda p:cf(os.environ['CLOUDFLARE_API_TOKEN'],os.environ['CLOUDFLARE_ACCOUNT_ID'],p)))
    if os.getenv('GROQ_API_KEY'):
        models=[]; primary=os.getenv('GROQ_TEXT_MODEL','openai/gpt-oss-120b')
        for m in [primary,'openai/gpt-oss-120b','openai/gpt-oss-20b','qwen/qwen3.6-27b']:
            if m and m not in models: models.append(m)
        for m in models: providers.append((f'Groq:{m}',lambda p,m=m:compat('Groq',os.environ['GROQ_API_KEY'],m,p)))
    if os.getenv('TOGETHER_API_KEY') and os.getenv('ENABLE_TOGETHER_PROVIDER','false').lower()=='true': providers.append(('Together',lambda p:compat('Together',os.environ['TOGETHER_API_KEY'],os.environ.get('TOGETHER_TEXT_MODEL','Qwen/Qwen3.5-9B'),p)))
    if os.getenv('QWENCLOUD_API_KEY'): providers.append(('QwenCloud',lambda p:qwencloud_long_story(os.environ['QWENCLOUD_API_KEY'],p)))
    if os.getenv('CEREBRAS_API_KEY') and os.getenv('CEREBRAS_FREE_ONLY','true').lower()=='true': providers.append(('Cerebras',lambda p:cerebras_generate(os.environ['CEREBRAS_API_KEY'],p)))
    if not providers: raise SystemExit('No AI provider credentials; long-form fallback is disabled')
    last=None
    for name,fn in providers:
        for attempt,prompt in enumerate((council_prompt,council_prompt+'\n'+REPAIR),1):
            try:
                result=fn(prompt)
                model=None
                if name=='QwenCloud': result,model=result
                d=validate(result); d['provider']=name; d['model']=model or (os.getenv('CEREBRAS_MODEL') if name=='Cerebras' else (os.getenv('GROQ_TEXT_MODEL') if name.startswith('Groq:') else None)); d['generation_attempt']=attempt; d['idea_council_winner']=winner
                OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f'LONG_STORY provider={name} model={model or d.get("model") or "default"} council_winner={winner["idea_id"]} scenes={d["scene_count"]} words={d["script_words"]}'); return
            except Exception as e:
                last=e; kind=classify_provider_error(e); print(f'{name} long-story attempt {attempt} failed [{kind}]: {e}')
                if kind in {'AUTH','ACCESS_OR_QUOTA','MODEL_NOT_FOUND'}: break
    raise SystemExit(f'All AI providers failed for long story: {last}')
if __name__=='__main__': generate()
