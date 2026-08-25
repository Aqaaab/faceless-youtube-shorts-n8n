#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

RUN=Path(os.environ.get('RUN_DIR','data/daily-production'))
IN=RUN/'idea_council.json'; OUT=RUN/'idea_judged.json'

WEIGHTS={'trend_score':.20,'curiosity_score':.20,'novelty_score':.20,'story_score':.15,'visual_score':.10,'short_score':.15}

def weighted(x): return round(sum(float(x.get(k,0))*w for k,w in WEIGHTS.items()),2)

def main():
    if not IN.exists(): raise SystemExit('IDEA_COUNCIL_MISSING')
    d=json.loads(IN.read_text())
    candidates=d.get('top_5',[])
    if len(candidates)<1: raise SystemExit('NO_IDEA_CANDIDATES')
    for x in candidates:
        x['judge_score']=weighted(x)
        x['judge_checks']={'has_hook':bool(x.get('hook')),'has_core_question':bool(x.get('core_question')),'independent_angle':bool(x.get('novel_angle')),'long_form_ready':float(x.get('story_score',0))>=70,'short_ready':float(x.get('short_score',0))>=70}
        x['judge_eligible']=all(x['judge_checks'].values())
    eligible=[x for x in candidates if x['judge_eligible']]
    if not eligible: raise SystemExit('NO_JUDGE_ELIGIBLE_IDEA')
    eligible.sort(key=lambda x:x['judge_score'],reverse=True)
    winner=eligible[0]
    out={'schema_version':'1.0','method':'independent-weighted-judge','candidates':candidates,'top_5':eligible[:5],'winner':winner,'winner_score':winner['judge_score']}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(f'IDEA_JUDGE=PASS winner={winner["idea_id"]} score={winner["judge_score"]}')
if __name__=='__main__': main()
