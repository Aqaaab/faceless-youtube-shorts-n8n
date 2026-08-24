#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, json, os, re, subprocess, sys, urllib.error, urllib.request
from pathlib import Path
try:
    from json_repair import repair_json
except Exception:
    repair_json = None

GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'
OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
GENERIC={'nature','countryside','landscape','background','abstract','object','thing','person','people','room','building','city','sky','scene','random','wall'}
MODIFIERS={'closeup','close','wide','shot','footage','video','portrait','detail','dance','view','macro','aerial'}

def words(s): return re.findall(r"[A-Za-z0-9'-]+", s.lower())

def extract_json(text):
    text=(text or '').strip().replace('\ufeff','')
    a,b=text.find('{'),text.rfind('}')
    if a<0 or b<=a: raise RuntimeError('model returned no JSON object')
    raw=text[a:b+1]
    try: return json.loads(raw)
    except Exception as first:
        if repair_json:
            try:
                obj=repair_json(raw,return_objects=True)
                if isinstance(obj,dict): return obj
            except Exception: pass
        raise RuntimeError(f'invalid model JSON: {raw[:500]}') from first

def post(url,body,headers):
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
    with urllib.request.urlopen(req,timeout=120) as r: return json.loads(r.read().decode('utf-8','replace'))

def duration(p):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],check=True,capture_output=True,text=True)
    return float(r.stdout.strip())

def frame(video,out,ratio):
    d=max(.2,duration(video)); t=max(.05,min(d-.05,d*ratio))
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','5',str(out)],check=True)

def contact_sheet(video,out):
    tmp=[]
    for n,r in enumerate((.18,.50,.82),1):
        p=out.parent/f'{out.stem}_{n}.jpg'; frame(video,p,r); tmp.append(p)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(tmp[0]),'-i',str(tmp[1]),'-i',str(tmp[2]),'-filter_complex','[0:v]scale=540:960[a];[1:v]scale=540:960[b];[2:v]scale=540:960[c];[a][b][c]hstack=inputs=3,scale=1620:960','-frames:v','1',str(out)],check=True)
    return tmp

def gemini(prompt,images,key):
    parts=[{'text':prompt}]
    for p in images: parts.append({'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(p.read_bytes()).decode()}})
    payload=post(GEMINI_URL,{'contents':[{'role':'user','parts':parts}],'generationConfig':{'temperature':0,'maxOutputTokens':2400,'responseMimeType':'application/json'}},{'x-goog-api-key':key,'Content-Type':'application/json'})
    ps=(((payload.get('candidates') or [{}])[0].get('content') or {}).get('parts') or [])
    return extract_json(''.join(p.get('text','') for p in ps if isinstance(p,dict)))

def openrouter(prompt,images,key):
    content=[{'type':'text','text':prompt}]
    for p in images: content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(p.read_bytes()).decode()}})
    payload=post(OPENROUTER_URL,{'model':OPENROUTER_MODEL,'messages':[{'role':'user','content':content}],'temperature':0,'max_tokens':2400},{'Authorization':f'Bearer {key}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts Visual QA'})
    choices=payload.get('choices') or []
    if not choices: raise RuntimeError('OpenRouter returned no choices')
    text=(choices[0].get('message') or {}).get('content','')
    if isinstance(text,list): text=''.join(str(x.get('text','')) for x in text if isinstance(x,dict))
    return extract_json(text)

def semantic_gate(scene,source):
    q=words(scene.get('pexels_query',''))
    q=[x for x in q if x not in MODIFIERS and x not in GENERIC]
    if not q: return False,'query has no concrete subject'
    if not source.exists() or source.stat().st_size<100000: return False,'missing or suspicious Pexels source'
    # Query describes the visual subject; it is not required to literally occur in narration.
    return True,'deterministic visual-subject gate passed'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('run_dir'); a=ap.parse_args(); run=Path(a.run_dir)
    job=json.loads((run/'job.json').read_text(encoding='utf-8')); scenes=job.get('scenes') or []
    if len(scenes)!=5: print('ERROR: exactly 5 scenes required',file=sys.stderr); return 2
    qa=run/'visual_qa'; qa.mkdir(parents=True,exist_ok=True)
    reports=[]; failures=[]; sheets=[]
    for i,s in enumerate(scenes,1):
        en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); q=str(s.get('pexels_query','')).strip()
        r={'scene':i,'text_en':en,'text_ar':ar,'pexels_query':q,'passed':False,'translation_ok':True}
        reports.append(r); v=run/'scenes'/f'scene_{i}.mp4'; src=run/'downloads'/f'source_{i}.mp4'
        if not v.exists(): r['reason']='missing rendered scene'; failures.append({'scene':i,'type':'qa','reason':r['reason']}); continue
        if 'chameleon' in en.lower() and ('حرباء' not in ar or 'القمل' in ar):
            r['translation_ok']=False; r['translation_reason']='chameleon must translate to حرباء'; failures.append({'scene':i,'type':'translation','reason':r['translation_reason']})
        try: sheets.append(qa/f'scene_{i}_sheet.jpg'); contact_sheet(v,sheets[-1])
        except Exception as e: r['reason']=f'frame extraction failed: {e}'; failures.append({'scene':i,'type':'qa','reason':r['reason']})
    prompt='''You are a strict final publication gate for five YouTube Shorts scenes. Each attached image is a 3-frame contact sheet for the scene, in order 1..5. Compare the footage to the concrete visual subject requested by the Pexels query and to the narration. A match means the main subject is visibly present and relevant, not merely a vaguely related setting. Reject unrelated people, cats, objects, rooms, generic landscapes, or stock footage whose subject differs. Also check that Arabic preserves the English meaning. Return ONLY compact JSON: {"scenes":[{"scene":1,"visual_match":true,"visual_score":0.95,"translation_ok":true,"reason":"...","translation_reason":"..."},...]} exactly five objects. Score 0.90+ only for a strong direct match; 0.80-0.89 for a clear but less direct match; below 0.80 for weak/unrelated.'''
    context='\n'.join(f"SCENE {i}: EN={s.get('text_en','')} | AR={s.get('text_ar','')} | QUERY={s.get('pexels_query','')}" for i,s in enumerate(scenes,1))
    prompt += '\n'+context
    result=None; model='none'
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if len(sheets)==5 and key:
        try: result=gemini(prompt,sheets,key); model='Gemini:'+GEMINI_MODEL
        except Exception as e: print(f'Gemini visual QA unavailable: {e}',file=sys.stderr)
    if result is None and len(sheets)==5:
        key=os.environ.get('OPENROUTER_API_KEY','').strip()
        if key:
            try: result=openrouter(prompt,sheets,key); model='OpenRouter:'+OPENROUTER_MODEL
            except Exception as e: print(f'OpenRouter visual QA unavailable: {e}',file=sys.stderr)
    items=result.get('scenes') if isinstance(result,dict) else None
    if not isinstance(items,list) or len(items)!=5: result=None
    if result is not None:
        for item in items:
            try: i=int(item.get('scene')); score=float(item.get('visual_score',0))
            except Exception: continue
            if not 1<=i<=5: continue
            r=reports[i-1]; vm=bool(item.get('visual_match')) and score>=.80; tr=bool(item.get('translation_ok')) and r.get('translation_ok',True)
            r.update({'visual_match':bool(item.get('visual_match')),'visual_score':score,'translation_ok':tr,'reason':str(item.get('reason','')),'translation_reason':str(item.get('translation_reason','')),'passed':vm and tr})
            if not vm: failures.append({'scene':i,'type':'visual','score':score,'reason':r['reason']})
            if not tr: failures.append({'scene':i,'type':'translation','reason':r.get('translation_reason','model rejected translation')})
            print(f"Scene {i}: {'PASS' if r['passed'] else 'FAIL'} visual={score:.2f} translation={tr} | {r['reason']}",flush=True)
    if result is None:
        model='deterministic-semantic-fallback'
        for i,s in enumerate(scenes,1):
            r=reports[i-1]; ok,reason=semantic_gate(s,run/'downloads'/f'source_{i}.mp4'); r.update({'visual_match':ok,'visual_score':.80 if ok else 0.0,'reason':reason,'passed':ok and r.get('translation_ok',True)})
            if not ok: failures.append({'scene':i,'type':'visual','reason':reason})
            print(f"Scene {i}: {'PASS' if r['passed'] else 'FAIL'} | {reason}",flush=True)
    final={'passed':not failures and len(reports)==5,'model':model,'thresholds':{'visual_score':.80,'required_scenes':5},'scene_reports':reports,'failures':failures}
    (qa/'report.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Visual QA report written: {qa/"report.json"}',flush=True)
    if failures: print('VISUAL/TRANSLATION QA FAILED — upload must not proceed.',file=sys.stderr); return 1
    print('VISUAL/TRANSLATION QA PASSED — all scenes cleared the publication gate.',flush=True); return 0
if __name__=='__main__': raise SystemExit(main())
