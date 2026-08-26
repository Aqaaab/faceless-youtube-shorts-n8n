#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
RUN_DIR.mkdir(parents=True, exist_ok=True)
MIN_WORDS = int(os.environ.get('LONG_MIN_WORDS', '1050'))
MAX_WORDS = int(os.environ.get('LONG_MAX_WORDS', '2100'))
SCENES = int(os.environ.get('LONG_TARGET_SCENES', '20'))

PROMPT = f'''Create ONE factual, high-retention YouTube long-form story in English. Return ONLY one JSON object, no markdown.
Create EXACTLY {SCENES} scenes. Each scene MUST contain text_en, text_ar, visual_subject, pexels_query, and beat.
Each text_en scene MUST contain 45-70 English words. Total English narration MUST be {MIN_WORDS}-{MAX_WORDS} words.
Use these beats across the story: hook, setup, mystery, escalation, evidence, reveal, payoff, ending; every beat must appear at least once.
text_en must contain English only. text_ar must be faithful Modern Standard Arabic. visual_subject must contain 2-5 concrete physical words. pexels_query must contain 3-7 concrete English words and match the scene.
Build a coherent story with a strong hook, escalating evidence, a clear reveal/payoff, and a concise ending. No fabricated quotes, unsupported absolute claims, filler, or CTA.
Include topic, category, title <=90 characters, a 3-5 sentence factual description, and 8-15 lowercase ASCII tags.
Target 55-60 English words per scene so the total naturally lands inside the required range.'''


def wc(s):
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", str(s)))


def validate(d):
    scenes = d.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != SCENES:
        raise ValueError(f'long story scene count invalid: expected {SCENES}')
    total = 0; beats = set()
    for i, s in enumerate(scenes, 1):
        if not isinstance(s, dict): raise ValueError(f'scene {i} not object')
        en = str(s.get('text_en', '')).strip(); ar = str(s.get('text_ar', '')).strip()
        vs = str(s.get('visual_subject', '')).strip(); q = str(s.get('pexels_query', '')).strip()
        beat = str(s.get('beat', '')).strip().lower()
        if not all((en, ar, vs, q, beat)): raise ValueError(f'scene {i} missing required fields')
        n = wc(en)
        if not 45 <= n <= 70: raise ValueError(f'scene {i} word count {n} outside 45-70')
        if re.search(r'[\u0600-\u06ff]', en) or not re.search(r'[\u0600-\u06ff]', ar): raise ValueError(f'scene {i} language contract failed')
        if not 2 <= len(vs.split()) <= 5 or not 3 <= len(q.split()) <= 7: raise ValueError(f'scene {i} visual/query length contract failed')
        if beat not in {'hook','setup','mystery','escalation','evidence','reveal','payoff','ending'}: raise ValueError(f'scene {i} invalid beat')
        total += n; beats.add(beat)
    if not MIN_WORDS <= total <= MAX_WORDS: raise ValueError(f'total narration {total} outside {MIN_WORDS}-{MAX_WORDS}')
    if len(beats) < 8: raise ValueError('missing story beats')
    title = str(d.get('title', '')).strip(); tags = d.get('tags', []); desc = str(d.get('description', '')).strip()
    if not title or len(title) > 90: raise ValueError('invalid long-form title')
    if not isinstance(tags, list) or not 8 <= len(tags) <= 15: raise ValueError('invalid tags')
    if any(not re.fullmatch(r'[a-z0-9_-]+', str(t)) for t in tags): raise ValueError('tags must be lowercase ASCII')
    if not 3 <= len([x for x in re.split(r'(?<=[.!?])\s+', desc) if x.strip()]) <= 5: raise ValueError('invalid description')
    d['script'] = ' '.join(s['text_en'].strip() for s in scenes)
    d['narration'] = d['script']; d['subtitle_ar'] = ' '.join(s['text_ar'].strip() for s in scenes)
    d['scene_count'] = SCENES; d['script_words'] = total; d['format'] = 'patent'; d['duration_target_minutes'] = [7, 15]
    return d


def main():
    from ai_router import build_long_story_router
    router = build_long_story_router()
    if not router.providers: raise SystemExit('NO_LONG_STORY_AI_PROVIDERS')
    last = None; excluded = set(); previous_error = ''
    for attempt in range(1, max(8, len(router.providers) * 2) + 1):
        feedback = f'\nPrevious validation failure: {previous_error}. Fix that exact failure.' if previous_error else ''
        try:
            result, provider, model = router.route(PROMPT + feedback, exclude=excluded)
            d = validate(result); d.update({'provider': provider, 'model': model, 'router': 'Aqaaab AI Router', 'router_task': 'long_story', 'generation_attempt': attempt})
            (RUN_DIR / 'job.json').write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'LONG_STORY_ROUTER=PASS provider={provider} scenes={SCENES} words={d["script_words"]} attempt={attempt}')
            return 0
        except Exception as e:
            last = e; previous_error = str(e); print(f'LONG_STORY_ROUTER attempt={attempt} failed: {e}')
            provider = locals().get('provider')
            if provider:
                try: router.report_validation_failure(provider, e)
                except Exception: pass
                excluded.add(provider)
    raise SystemExit(f'LONG_STORY_ROUTER exhausted providers: {last}')

if __name__ == '__main__':
    raise SystemExit(main())
