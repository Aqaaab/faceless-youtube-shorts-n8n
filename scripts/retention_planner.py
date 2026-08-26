#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path(os.environ.get('RUN_DIR','data/run'))

def sentence_words(text):
    return len(re.findall(r"\b\w+\b", text or ''))

def main():
    story = json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    scenes = story.get('scenes') or []
    if not scenes:
        raise SystemExit('RETENTION_INPUT_MISSING')
    beats=[]; risks=[]; interrupts=[]
    for i, scene in enumerate(scenes, 1):
        text = str(scene.get('narration') or scene.get('voiceover') or scene.get('text') or scene.get('script') or '')
        words = sentence_words(text)
        risk = 0
        if words < 20: risk += 25
        if words > 130: risk += 10
        if i > 1 and i % 5 == 0: interrupts.append({'scene':i,'type':'pattern_interrupt'})
        if not text.strip(): risk = 100
        risks.append({'scene':i,'risk':min(100,risk),'words':words})
        beats.append({'scene':i,'purpose':'setup' if i<=2 else 'escalation' if i < len(scenes)-3 else 'payoff','words':words})
    avg = sum(r['risk'] for r in risks)/len(risks)
    payload={'stage':'retention_planner','beat_map':beats,'pattern_interrupts':interrupts,'retention_risk':round(avg,2),'high_risk_scenes':[x['scene'] for x in risks if x['risk']>=40]}
    (RUN_DIR/'retention_simulation.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"RETENTION_PLANNER=PASS risk={payload['retention_risk']} high_risk={len(payload['high_risk_scenes'])}")
    return 0
if __name__=='__main__': raise SystemExit(main())
