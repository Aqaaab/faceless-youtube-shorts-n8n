#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); JOB=RUN_DIR/'job.json'
GEN=Path(__file__).with_name('generate_job.py')
spec=importlib.util.spec_from_file_location('generate_job',GEN); gen=importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
PROMPT='''Rewrite the existing YouTube Shorts script for natural spoken delivery. The goal is a human-like conversational storyteller, not an article being read aloud. Keep every factual claim, qualifier, topic, and scene order. Make the English sound like someone talking directly to one curious viewer: use contractions, short natural phrases, occasional rhetorical questions, curiosity, emphasis, and varied sentence rhythm. Do not add fake facts, CTA, emojis, or slang that sounds forced. Preserve exactly 5 scenes, 13-19 English words per scene, and 75-95 words total. Provide faithful Modern Standard Arabic translations for the rewritten English. Return ONLY JSON with scenes, each containing text_en, text_ar, visual_subject, pexels_query. Do not put stage directions or [emotion] tags in text_en.'''
def call(name):
    if name=='OpenRouter' and os.getenv('OPENROUTER_API_KEY'):
        x=gen.post(gen.OPENROUTER_URL,{'model':gen.OPENROUTER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+JOB.read_text(encoding='utf-8')}],'temperature':.55,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["OPENROUTER_API_KEY"]}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Conversational Voice Director'})
        return gen.extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
    if name=='Gemini' and os.getenv('GEMINI_API_KEY'):
        x=gen.post(gen.GEMINI_URL,{'contents':[{'role':'user','parts':[{'text':PROMPT+'\n\nCURRENT JOB:\n'+JOB.read_text(encoding='utf-8')}]}],'generationConfig':{'temperature':.55,'maxOutputTokens':5000,'responseMimeType':'application/json'}},{'x-goog-api-key':os.environ['GEMINI_API_KEY'],'Content-Type':'application/json'})
        return gen.extract(''.join(str(p.get('text','')) for p in (((x.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
    if name=='Groq' and os.getenv('GROQ_API_KEY'):
        return gen.compat('Groq',os.environ['GROQ_API_KEY'],gen.GROQ_MODEL) if False else gen.extract(gen.post('https://api.groq.com/openai/v1/chat/completions',{'model':gen.GROQ_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+JOB.read_text(encoding='utf-8')}],'temperature':.55,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["GROQ_API_KEY"]}','Content-Type':'application/json'}).get('choices',[{}])[0].get('message',{}).get('content',''))
    if name=='Together' and os.getenv('TOGETHER_API_KEY'):
        return gen.extract(gen.post('https://api.together.ai/v1/chat/completions',{'model':gen.TOGETHER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT+'\n\nCURRENT JOB:\n'+JOB.read_text(encoding='utf-8')}],'temperature':.55,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {os.environ["TOGETHER_API_KEY"]}','Content-Type':'application/json'}).get('choices',[{}])[0].get('message',{}).get('content',''))
    return None

def validate(d):
    sc=d.get('scenes')
    if not isinstance(sc,list) or len(sc)!=5: raise ValueError('5 scenes required')
    words=[]
    for i,s in enumerate(sc,1):
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip()
        if not 13<=gen.word_count(en)<=19: raise ValueError(f'scene {i} word count')
        if re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language')
        if gen.ABS_EN.search(en) or gen.ABS_AR.search(ar): raise ValueError(f'scene {i} absolute claim')
        words.append(en)
    if not 75<=gen.word_count(' '.join(words))<=95: raise ValueError('total word count')

def main():
    if not JOB.exists(): raise SystemExit('job.json missing')
    original=json.loads(JOB.read_text(encoding='utf-8'))
    errors=[]
    for name in ('OpenRouter','Gemini','Groq','Together'):
        try:
            d=call(name)
            if not d: continue
            validate(d)
            merged={**original,**d,'provider':original.get('provider',name),'voice_style':'conversational'}
            merged['script']=' '.join(s['text_en'].strip() for s in merged['scenes']); merged['narration']=merged['script']; merged['subtitle_ar']=' '.join(s['text_ar'].strip() for s in merged['scenes']); merged['hook']=merged['scenes'][0]['text_en'].strip()
            JOB.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'Voice Director PASS provider={name} conversational=true words={gen.word_count(merged["script"])}')
            return 0
        except Exception as e:
            errors.append(f'{name}: {e}'); print(f'Voice Director {name} failed: {e}')
    print('Voice Director unavailable; keeping original script. '+ ' | '.join(errors))
    return 0
if __name__=='__main__': raise SystemExit(main())
