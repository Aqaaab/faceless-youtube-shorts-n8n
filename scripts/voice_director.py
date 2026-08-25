#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); JOB=RUN_DIR/'job.json'
GEN=Path(__file__).with_name('generate_job.py')
spec=importlib.util.spec_from_file_location('generate_job',GEN); gen=importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
PROMPT='''Rewrite the existing YouTube Shorts script for natural spoken delivery. The goal is a human-like conversational storyteller, not an article being read aloud. Keep every factual claim, qualifier, topic, and scene order. Make the English sound like someone talking directly to one curious viewer: use contractions, short natural phrases, occasional rhetorical questions, curiosity, emphasis, and varied sentence rhythm. Do not add fake facts, CTA, emojis, or forced slang. Preserve exactly the existing number of scenes, 8-18 English words per scene, and 80-110 words total. Provide faithful Modern Standard Arabic translations for the rewritten English. Return ONLY JSON with scenes, each containing text_en, text_ar, visual_subject, pexels_query. Do not put stage directions or [emotion] tags in text_en.'''
def call(name):
    current=JOB.read_text(encoding='utf-8')
    if name=='OpenRouter' and os.getenv('OPENROUTER_API_KEY'):
        x=gen.post(gen.OPENROUTER_URL,{'model':gen.OPENROUTER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+current}],'temperature':.45,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["OPENROUTER_API_KEY"]}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Conversational Voice Director'})
        return gen.extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
    if name=='Gemini' and os.getenv('GEMINI_API_KEY'):
        x=gen.post(gen.GEMINI_URL,{'contents':[{'role':'user','parts':[{'text':PROMPT+'\n\nCURRENT JOB:\n'+current}]}],'generationConfig':{'temperature':.45,'maxOutputTokens':5000,'responseMimeType':'application/json'}},{'x-goog-api-key':os.environ['GEMINI_API_KEY'],'Content-Type':'application/json'})
        return gen.extract(''.join(str(p.get('text','')) for p in (((x.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
    if name=='Groq' and os.getenv('GROQ_API_KEY'):
        x=gen.post('https://api.groq.com/openai/v1/chat/completions',{'model':gen.GROQ_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+current}],'temperature':.45,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["GROQ_API_KEY"]}','Content-Type':'application/json'})
        return gen.extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
    if name=='Together' and os.getenv('TOGETHER_API_KEY'):
        x=gen.post('https://api.together.ai/v1/chat/completions',{'model':gen.TOGETHER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+current}],'temperature':.45,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["TOGETHER_API_KEY"]}','Content-Type':'application/json'})
        return gen.extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
    return None

def validate(d,expected_scenes):
    sc=d.get('scenes')
    if not isinstance(sc,list) or len(sc)!=expected_scenes: raise ValueError(f'{expected_scenes} scenes required')
    words=[]
    for i,s in enumerate(sc,1):
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip()
        if not 8<=gen.word_count(en)<=18: raise ValueError(f'scene {i} word count')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language')
        if not vs or not 1<=len(vs.split())<=3: raise ValueError(f'scene {i} visual_subject')
        if not q or not 1<=len(q.split())<=5: raise ValueError(f'scene {i} pexels_query')
        if gen.ABS_EN.search(en) or gen.ABS_AR.search(ar): raise ValueError(f'scene {i} absolute claim')
        words.append(en)
    if not 80<=gen.word_count(' '.join(words))<=110: raise ValueError('total word count')

def main():
    if not JOB.exists(): raise SystemExit('job.json missing')
    original=json.loads(JOB.read_text(encoding='utf-8')); expected=len(original.get('scenes') or [])
    errors=[]
    if not 5<=expected<=10: raise SystemExit(f'job scene count {expected} outside production bounds')
    for name in ('OpenRouter','Gemini','Groq','Together'):
        try:
            d=call(name)
            if not d: continue
            validate(d,expected)
            merged={**original,**d,'provider':original.get('provider',name),'voice_style':'conversational'}
            merged['script']=' '.join(s['text_en'].strip() for s in merged['scenes']); merged['narration']=merged['script']; merged['subtitle_ar']=' '.join(s['text_ar'].strip() for s in merged['scenes']); merged['hook']=merged['scenes'][0]['text_en'].strip(); merged['scene_count']=expected
            JOB.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'Voice Director PASS provider={name} conversational=true words={gen.word_count(merged["script"])} scenes={expected}')
            return 0
        except Exception as e:
            errors.append(f'{name}: {e}'); print(f'Voice Director {name} failed: {e}')
    print('Voice Director unavailable; keeping original AI-generated script. '+ ' | '.join(errors))
    return 0
if __name__=='__main__': raise SystemExit(main())