#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path(__import__('os').environ.get('RUN_DIR', 'data/run'))

STOP_WORDS = {'the','a','an','and','or','but','this','that','with','from','into','when','what','how','why'}

def first_sentences(text: str, limit: int = 8) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', text.strip()))
    return [p.strip() for p in parts if p.strip()][:limit]

def score_hook(text: str) -> float:
    t = text.strip()
    lower = t.lower()
    words = re.findall(r"[A-Za-z0-9']+", t)
    score = 35.0
    if 8 <= len(words) <= 24: score += 15
    if '?' in t: score += 10
    if any(x in lower for x in ('but','until','didn\'t','never','secret','nobody','wrong','hidden','suddenly')): score += 15
    if re.search(r'\b\d{1,3}\b', t): score += 6
    if any(w not in STOP_WORDS for w in words): score += min(8, len(set(w.lower() for w in words if w.lower() not in STOP_WORDS)) / 3)
    if t.count(',') <= 2: score += 5
    if len(t) > 180: score -= 12
    return max(0.0, min(100.0, round(score, 2)))

def main() -> int:
    story = json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    text = str(story.get('script') or story.get('narration') or '')
    candidates = first_sentences(text)
    if not candidates:
        raise SystemExit('HOOK_INPUT_MISSING')
    scored = sorted(({'hook': h, 'score': score_hook(h)} for h in candidates), key=lambda x: x['score'], reverse=True)
    top = scored[:10]
    payload = {'stage':'hook_optimizer','candidate_count':len(top),'hook_candidates':top,'selected_hook':top[0]['hook'],'selected_score':top[0]['score']}
    (RUN_DIR/'hook_candidates.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"HOOK_OPTIMIZER=PASS candidates={len(top)} score={top[0]['score']}")
    return 0

if __name__ == '__main__': raise SystemExit(main())
