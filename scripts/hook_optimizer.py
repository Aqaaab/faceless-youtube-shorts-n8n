#!/usr/bin/env python3
from __future__ import annotations
import json, re, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))

def score_hook(text: str) -> float:
    t = text.strip(); lower = t.lower(); words = re.findall(r"[A-Za-z0-9']+", t)
    score = 35.0
    if 8 <= len(words) <= 24: score += 15
    if '?' in t: score += 10
    if any(x in lower for x in ('but','until','didn\'t','never','secret','nobody','wrong','hidden','suddenly')): score += 15
    if re.search(r'\b\d{1,3}\b', t): score += 6
    if len(t) > 180: score -= 12
    if len(set(w.lower() for w in words)) >= max(6, len(words)//2): score += 8
    return max(0.0, min(100.0, round(score, 2)))

def candidates_from_context(context: dict) -> list[str]:
    topic=str(context.get('topic') or context.get('title') or 'this mystery').strip()
    q=str(context.get('core_question') or context.get('question') or '').strip()
    angle=str(context.get('novel_angle') or '').strip()
    base=[
        f"What if the story you know about {topic} is missing the most important detail?",
        f"Why does {topic} still raise one question nobody can answer?",
        f"The strangest part of {topic} happened after everyone thought the case was over.",
        f"There is one overlooked clue in {topic} that changes the timeline.",
        f"The truth about {topic} is more complicated than the popular version." ]
    if q: base.insert(0,q)
    if angle: base.insert(1,angle)
    return base

def main() -> int:
    source=RUN_DIR/'idea_judged.json'
    if not source.is_file(): source=RUN_DIR/'daily_plan.json'
    if not source.is_file(): raise SystemExit('HOOK_INPUT_MISSING')
    data=json.loads(source.read_text(encoding='utf-8'))
    context=data.get('winner') if isinstance(data.get('winner'),dict) else data.get('daily_long_video',data)
    if not isinstance(context,dict): context={}
    raw=context.get('hook_candidates') or context.get('hooks') or candidates_from_context(context)
    scored=sorted(({'hook':str(h),'score':score_hook(str(h))} for h in raw if str(h).strip()),key=lambda x:x['score'],reverse=True)
    if not scored: raise SystemExit('HOOK_CANDIDATES_EMPTY')
    payload={'stage':'hook_optimizer','input':'topic_council','candidate_count':len(scored[:10]),'hook_candidates':scored[:10],'selected_hook':scored[0]['hook'],'selected_score':scored[0]['score']}
    (RUN_DIR/'hook_candidates.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"HOOK_OPTIMIZER=PASS candidates={len(scored[:10])} score={scored[0]['score']}")
    return 0
if __name__=='__main__': raise SystemExit(main())
