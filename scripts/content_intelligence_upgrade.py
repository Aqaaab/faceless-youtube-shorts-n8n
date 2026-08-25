#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, hashlib
from pathlib import Path
RUN=Path(os.environ.get('RUN_DIR','data/run')); RUN.mkdir(parents=True,exist_ok=True)
def load(name, default=None):
 p=RUN/name
 if not p.exists(): return {} if default is None else default
 return json.loads(p.read_text(encoding='utf-8'))
def save(name,data): (RUN/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def words(s): return re.findall(r"[A-Za-z][A-Za-z0-9'-]*",str(s))
def tokens(s): return set(x.lower() for x in re.findall(r'[a-z0-9]+',str(s)) if len(x)>3)
def competitor():
 trends=load('trend_candidates.json',[]); items=trends.get('items',trends.get('trends',[])) if isinstance(trends,dict) else trends; rows=[]
 for x in items[:50]:
  title=str(x.get('title',x.get('topic',''))).strip()
  if title: rows.append({'pattern':title,'momentum_score':round(min(100,float(x.get('trend_score',x.get('score',50)) or 50)),2),'pattern_type':'topic/title pattern','copy_policy':'pattern only; never copy title, script, scenes or claims'})
 rows.sort(key=lambda x:x['momentum_score'],reverse=True); save('competitor_intelligence.json',{'schema_version':'1.0','source':'trend_candidates','top_patterns':rows[:20]})
def tournament():
 c=load('idea_council.json'); ideas=c.get('top_5',[])
 for x in ideas: x['round_1']=round(.35*float(x.get('trend_score',0))+.25*float(x.get('curiosity_score',0))+.20*float(x.get('novelty_score',0))+.20*float(x.get('story_score',0)),2)
 ideas.sort(key=lambda x:x['round_1'],reverse=True); finalists=ideas[:5]
 for x in finalists: x['tournament_score']=round(.30*x['round_1']+.20*float(x.get('visual_score',0))+.20*float(x.get('short_score',0))+.30*float(x.get('performance_prior',0) or 0),2)
 finalists.sort(key=lambda x:x['tournament_score'],reverse=True); winner=(finalists[0] if finalists else c.get('winner',{})).copy(); winner['status']='winner'
 save('idea_tournament.json',{'schema_version':'1.0','rounds':3,'finalists':finalists,'winner':winner,'selection_policy':'Fresh trend evidence dominates when learning data is sparse.'}); save('idea_council.json',{**c,'winner':winner,'tournament_applied':True})
 judged=load('idea_judged.json')
 if judged: save('idea_judged.json',{**judged,'winner':winner,'winner_score':winner.get('tournament_score',judged.get('winner_score',0)),'tournament_applied':True})
def retention():
 story=load('long_story.json'); rows=[]; risk=[]
 for idx,s in enumerate(story.get('scenes',[]),1):
  text=str(s.get('text_en','')); n=len(words(text)); beat=str(s.get('beat','')).lower(); score=75+(15 if idx==1 else 0)+(8 if beat in {'mystery','escalation','reveal'} else 3 if beat in {'setup','evidence'} else 0)-(15 if n<35 or n>80 else 0)-(5 if not any(k in text.lower() for k in ('why','but','until','revealed','discovered','however','mystery')) else 0); score=max(0,min(100,score)); rows.append({'scene':idx,'retention_score':score,'beat':beat,'word_count':n}); risk += [idx] if score<70 else []
 save('retention_simulation.json',{'schema_version':'1.0','method':'preproduction heuristic','scene_scores':rows,'risk_scenes':risk,'revision_required':bool(risk),'note':'Prediction only; post-publish analytics remain authoritative.'})
def visual():
 story=load('long_story.json'); out=[]
 for i,s in enumerate(story.get('scenes',[]),1):
  subject=str(s.get('visual_subject','')).strip(); query=str(s.get('pexels_query','')).strip() or ' '.join(words(subject)[:5]) or 'cinematic documentary scene'; query=' '.join(query.split()[:7]); out.append({'scene':i,'visual_subject':subject,'pexels_query':query,'semantic_terms':list(tokens(subject+' '+query))[:10],'diversity_key':hashlib.sha1((subject+query).encode()).hexdigest()[:10]})
 save('visual_intelligence.json',{'schema_version':'1.0','engine':'semantic-query-v1','scenes':out,'diversity_target':0.18})
def shorts():
 story=load('long_story.json'); scenes=story.get('scenes',[]); candidates=[]
 for i,s in enumerate(scenes):
  text=str(s.get('text_en','')); beat=str(s.get('beat','')).lower(); sc=40+(25 if i==0 else 0)+(15 if beat in {'mystery','escalation','reveal'} else 5 if beat in {'evidence','payoff'} else 0)+min(20,len(tokens(text))); candidates.append({'scene_start':i+1,'scene_end':min(i+2,len(scenes)),'short_score':min(100,sc),'hook':text})
 candidates.sort(key=lambda x:x['short_score'],reverse=True); final=[]
 for c in candidates:
  if any(abs(c['scene_start']-x['scene_start'])<=1 for x in final): continue
  final.append(c)
  if len(final)==4: break
 if len(final)<4: raise SystemExit('SHORTS_INTELLIGENCE_NEEDS_FOUR_CANDIDATES')
 viral=load('viral_plan.json'); original=viral.get('shorts',[])
 for n,x in enumerate(final,1):
  source=next((s for s in original if s.get('scene_start')==x['scene_start']),{}); x.update({k:v for k,v in source.items() if k not in x}); x['short_number']=n
 save('shorts_intelligence.json',{'schema_version':'1.0','candidate_count':len(candidates),'selected':final,'selection_policy':'hook + narrative beat + standalone value'}); save('viral_plan.json',{**viral,'shorts':final,'shorts_intelligence_applied':True})
def packaging():
 story=load('long_story.json'); title=str(story.get('title','')); hook=str((story.get('scenes') or [{}])[0].get('text_en','')); base=title or 'The Story Nobody Expected'; variants=[{'title':base[:90],'hook':hook[:140],'angle':'clear curiosity'},{'title':('The Detail They Missed: '+base)[:90],'hook':hook[:140],'angle':'information gap'},{'title':('What Really Happened? '+base)[:90],'hook':hook[:140],'angle':'open question'}]
 for v in variants: v['score']=round(min(100,45+len(tokens(v['title']))*2+min(20,len(tokens(v['hook'])))),2)
 variants.sort(key=lambda x:x['score'],reverse=True); save('packaging_candidates.json',{'schema_version':'1.0','candidates':variants,'winner':variants[0]})
def thumbnails():
 p=load('packaging_candidates.json'); story=load('long_story.json'); subject=str(story.get('topic',story.get('title','story'))); concepts=[]
 for i,v in enumerate(p.get('candidates',[])[:5],1): concepts.append({'concept_id':f'th-{i}','title':v['title'],'visual_prompt':f'cinematic documentary thumbnail, one focal subject, high contrast, clear silhouette, no small text, mobile readable, theme: {subject}','mobile_readability':90-i*3,'curiosity_score':v['score']})
 concepts.sort(key=lambda x:x['mobile_readability']+x['curiosity_score'],reverse=True); save('thumbnail_candidates.json',{'schema_version':'1.0','concepts':concepts,'winner':concepts[0] if concepts else None,'render_provider':'existing image pipeline'})
def main():
 phase=os.getenv('CONTENT_INTELLIGENCE_PHASE','all')
 if phase in ('pre','all'): competitor(); tournament()
 if phase in ('post','all'): retention(); visual(); shorts(); packaging(); thumbnails()
 print(f'CONTENT_INTELLIGENCE_UPGRADE=PASS phase={phase}')
if __name__=='__main__': main()
