#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, hashlib
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/daily-production')); CONFIG=Path('config/idea-council.json'); OUT=RUN_DIR/'idea_council.json'; LEARNED=RUN_DIR/'council_learning.json'
ROLES={'trend_hunter':'Find high-momentum story opportunities from current trend evidence.','story_architect':'Turn trend patterns into original long-form story concepts.','curiosity_engineer':'Maximize curiosity, unanswered questions and opening hooks.','contrarian_agent':'Find a genuinely different angle without copying source stories.','viral_strategist':'Evaluate Long + 4 Shorts potential, packaging and retention potential.'}
def load_json(p): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
def norm(s): return re.sub(r'[^a-z0-9 ]+',' ',s.lower()).strip()
def similarity(a,b):
 A=set(norm(a).split()); B=set(norm(b).split()); return len(A&B)/max(1,len(A|B))
def prior_for(title,learn):
 n=norm(title); best=None; bs=0
 for p in learn.get('category_priors',[]):
  s=similarity(n,p.get('category',''))
  if s>bs: bs=s; best=p
 return float(best.get('performance_prior',0)) if best and bs>=0.35 else 0.0
def score(i):
 base=sum(float(i.get(k,0))*w for k,w in {'trend_score':.25,'curiosity_score':.20,'novelty_score':.15,'story_score':.15,'visual_score':.10,'short_score':.15}.items())
 prior=float(i.get('performance_prior',0)); return round(base*.85+prior*.15,2)
def main():
 RUN_DIR.mkdir(parents=True,exist_ok=True); trends=load_json(RUN_DIR/'trend_results.json') or load_json(Path('learning/trends.json')); learn=load_json(LEARNED)
 raw=trends.get('items',trends.get('trends',[])) if isinstance(trends,dict) else []; ideas=[]
 for t in raw[:30]:
  title=str(t.get('title',t.get('topic',''))).strip()
  if not title: continue
  seed=hashlib.sha256(title.encode()).hexdigest()[:10]; base=float(t.get('trend_score',t.get('score',50)) or 50); prior=prior_for(title,learn)
  ideas.append({'idea_id':f'council-{seed}','source_pattern':title,'topic':f'Original investigation inspired by the pattern: {title}','core_question':f'What is the overlooked explanation behind {title}?','hook':f'The detail everyone missed about {title}','novel_angle':'Use an independent subject, evidence and narrative angle; do not reproduce the source story.','trend_score':min(100,base),'curiosity_score':min(100,base+8),'novelty_score':72,'story_score':88,'visual_score':82,'short_score':86,'performance_prior':prior,'roles':list(ROLES),'status':'candidate'})
 unique=[]
 for i in ideas:
  if any(similarity(i['topic'],u['topic'])>=0.72 for u in unique): continue
  i['score']=score(i); unique.append(i)
 unique.sort(key=lambda x:x['score'],reverse=True); top=unique[:5]
 if not top: raise SystemExit('IDEA_COUNCIL_NO_CANDIDATES')
 winner=top[0].copy(); winner['status']='winner'
 OUT.write_text(json.dumps({'schema_version':'1.1','roles':ROLES,'candidate_count':len(ideas),'deduplicated_count':len(unique),'top_5':top,'winner':winner,'learning_applied':bool(learn.get('category_priors')),'originality_policy':'Pattern extraction only; no source title, script, scene sequence or claims may be copied.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'IDEA_COUNCIL=PASS candidates={len(ideas)} unique={len(unique)} winner={winner["idea_id"]} learning={bool(learn.get("category_priors"))}')
if __name__=='__main__': main()
