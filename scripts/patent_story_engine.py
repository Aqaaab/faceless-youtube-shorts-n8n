#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'long_story.json'
MIN_WORDS=int(os.environ.get('LONG_MIN_WORDS','1050'))
MAX_WORDS=int(os.environ.get('LONG_MAX_WORDS','2100'))
MIN_SCENES=int(os.environ.get('LONG_MIN_SCENES','18'))
MAX_SCENES=int(os.environ.get('LONG_MAX_SCENES','30'))

PROMPT='''Create one factual or clearly framed true-story YouTube long-form story in English. Target 7-15 minutes. Return ONLY JSON. Use 18-30 scenes. Each scene must contain text_en (45-90 words), text_ar (faithful Arabic translation), visual_subject (2-5 concrete physical words), pexels_query (3-7 concrete words), and beat (hook/setup/mystery/escalation/evidence/reveal/payoff/ending). The complete narration must be 1050-2100 English words. Structure: Hook in the first scene, setup, central mystery/question, escalating discoveries, evidence, reveal/payoff, concise ending. No fabricated quotes, no absolute claims, no filler, no CTA. Include topic, category, title (<=90 chars), description (3-5 specific sentences), and 8-15 lowercase ASCII tags.''' 

def wc(s): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(s)))

def validate(d):
    sc=d.get('scenes')
    if not isinstance(sc,list) or not MIN_SCENES<=len(sc)<=MAX_SCENES: raise ValueError('long story scene count invalid')
    words=0
    beats=[]
    for i,s in enumerate(sc,1):
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); beat=str(s.get('beat','')).strip().lower()
        if not all([en,ar,vs,q,beat]): raise ValueError(f'scene {i} missing required fields')
        n=wc(en)
        if not 45<=n<=90: raise ValueError(f'scene {i} word count {n} outside 45-90')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language contract failed')
        words+=n; beats.append(beat)
    if not MIN_WORDS<=words<=MAX_WORDS: raise ValueError(f'long narration words {words} outside {MIN_WORDS}-{MAX_WORDS}')
    required=['hook','setup','mystery','escalation','evidence','reveal','payoff','ending']
    missing=[b for b in required if b not in beats]
    if missing: raise ValueError('missing story beats: '+','.join(missing))
    title=str(d.get('title','')).strip()
    if not title or len(title)>90: raise ValueError('invalid long-form title')
    d['script']=' '.join(s['text_en'].strip() for s in sc); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in sc); d['scene_count']=len(sc); d['script_words']=words; d['format']='patent'; d['duration_target_minutes']=[7,15]
    return d

def generate():
    # Uses the already validated multi-provider generator contract without changing its production fallback policy.
    from generate_job import openrouter,gemini,cf,compat
    providers=[]
    if os.getenv('OPENROUTER_API_KEY'): providers.append(('OpenRouter',lambda:openrouter(os.environ['OPENROUTER_API_KEY'],PROMPT)))
    if os.getenv('GEMINI_API_KEY'): providers.append(('Gemini',lambda:gemini(os.environ['GEMINI_API_KEY'],PROMPT)))
    if os.getenv('CLOUDFLARE_API_TOKEN') and os.getenv('CLOUDFLARE_ACCOUNT_ID'): providers.append(('Cloudflare',lambda:cf(os.environ['CLOUDFLARE_API_TOKEN'],os.environ['CLOUDFLARE_ACCOUNT_ID'],PROMPT)))
    if os.getenv('GROQ_API_KEY'): providers.append(('Groq',lambda:compat('Groq',os.environ['GROQ_API_KEY'],os.environ.get('GROQ_TEXT_MODEL','qwen/qwen3.6-27b'),PROMPT)))
    if os.getenv('TOGETHER_API_KEY'): providers.append(('Together',lambda:compat('Together',os.environ['TOGETHER_API_KEY'],os.environ.get('TOGETHER_TEXT_MODEL','Qwen/Qwen3.5-9B'),PROMPT)))
    if not providers: raise SystemExit('No AI provider credentials; long-form fallback is disabled')
    last=None
    for name,fn in providers:
        try:
            d=validate(fn()); d['provider']=name; OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f'LONG_STORY provider={name} scenes={d["scene_count"]} words={d["script_words"]}'); return
        except Exception as e:
            last=e; print(f'{name} long-story attempt failed: {e}')
    raise SystemExit(f'All AI providers failed for long story: {last}')

if __name__=='__main__': generate()
