#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, urllib.error, urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
RUN_DIR.mkdir(parents=True, exist_ok=True)
MIN_WORDS = int(os.environ.get('LONG_MIN_WORDS', '1050'))
MAX_WORDS = int(os.environ.get('LONG_MAX_WORDS', '2100'))
SCENES = int(os.environ.get('LONG_TARGET_SCENES', '20'))
PROVIDER_SCHEMA_RETRIES = max(1, int(os.environ.get('LONG_PROVIDER_SCHEMA_RETRIES', '3')))

PROMPT = f'''Create ONE factual, high-retention YouTube long-form story in English. Return ONLY one JSON object, no markdown.
Create EXACTLY {SCENES} scenes. Each scene MUST contain text_en, text_ar, visual_subject, pexels_query, and beat.
Each text_en scene MUST contain 45-70 English words. Target 55-60 words per scene.
Total English narration MUST be {MIN_WORDS}-{MAX_WORDS} words.
Use these beats across the story: hook, setup, mystery, escalation, evidence, reveal, payoff, ending; every beat must appear at least once.
text_en must contain English only. text_ar must be faithful Modern Standard Arabic. visual_subject must contain 2-5 concrete physical words. pexels_query must contain 3-7 concrete English words and match the scene.
Build a coherent story with a strong hook, escalating evidence, a clear reveal/payoff, and a concise ending. No fabricated quotes, unsupported absolute claims, filler, or CTA.
Include topic, category, title <=90 characters, a 3-5 sentence factual description, and 8-15 lowercase ASCII tags.
Before returning JSON, internally verify all scene counts, per-scene word counts, total word count, language fields, beats, and metadata.'''


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


def _mistral(prompt: str):
    key = os.getenv('MISTRAL_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Mistral API key missing')
    body = {
        'model': os.getenv('MISTRAL_MODEL', 'mistral-small-latest'),
        'messages': [
            {'role': 'system', 'content': 'Return exactly one JSON object. No markdown.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.15,
        'max_tokens': 12000,
        'response_format': {'type': 'json_object'},
    }
    req = urllib.request.Request(
        'https://api.mistral.ai/v1/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        payload = json.loads(r.read().decode('utf-8', 'replace'))
    content = ((payload.get('choices') or [{}])[0].get('message') or {}).get('content', '')
    if isinstance(content, list):
        content = ''.join(str(x.get('text', '')) if isinstance(x, dict) else str(x) for x in content)
    text = str(content).strip()
    a, b = text.find('{'), text.rfind('}')
    if a < 0 or b <= a:
        raise RuntimeError('Mistral returned no JSON object')
    return json.loads(text[a:b + 1])


def main():
    from ai_router import build_long_story_router
    router = build_long_story_router()
    providers = list(router.providers)
    if os.getenv('MISTRAL_API_KEY'):
        from ai_router import Provider
        providers.insert(0, Provider('Mistral', ['long_story'], 0, True, _mistral, model=os.getenv('MISTRAL_MODEL', 'mistral-small-latest')))
    router.providers = providers
    if not router.providers: raise SystemExit('NO_LONG_STORY_AI_PROVIDERS')

    last = None
    excluded = set()
    for provider_round in range(1, len(router.providers) + 1):
        provider_excluded_before = set(excluded)
        for schema_try in range(1, PROVIDER_SCHEMA_RETRIES + 1):
            previous_error = '' if not last else str(last)
            feedback = ''
            if previous_error:
                feedback = f'''\nPREVIOUS VALIDATION FAILURE — repair it before returning JSON:\n{previous_error}\nDo not repeat the same error. Recount every scene and the total narration.'''
            try:
                result, provider, model = router.route(PROMPT + feedback, exclude=excluded)
                d = validate(result)
                d.update({'provider': provider, 'model': model, 'router': 'Aqaaab AI Router', 'router_task': 'long_story', 'generation_attempt': schema_try})
                (RUN_DIR / 'job.json').write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                print(f'LONG_STORY_ROUTER=PASS provider={provider} scenes={SCENES} words={d["script_words"]} try={schema_try}')
                return 0
            except Exception as e:
                last = e
                print(f'LONG_STORY_ROUTER provider-attempt={provider_round}.{schema_try} failed: {e}')
                provider = locals().get('provider')
                if provider:
                    try: router.report_validation_failure(provider, e)
                    except Exception: pass
                # Schema/content failures get another attempt from the same provider with explicit feedback.
                # Transport/auth/quota failures are naturally skipped by the router on the next route call.
                msg = str(e).lower()
                schema_failure = any(x in msg for x in ('word count', 'language contract', 'scene count', 'missing story beats', 'invalid long-form', 'invalid tags', 'required fields', 'visual/query length', 'invalid beat'))
                if not schema_failure:
                    break
                time.sleep(min(2, schema_try))
        # After the provider has had its repair budget, exclude it and move to the next provider.
        if provider_round <= len(router.providers):
            for p in router.providers:
                if p.name not in provider_excluded_before and (not excluded or p.name == locals().get('provider')):
                    if p.name == locals().get('provider'):
                        excluded.add(p.name)
                        break
    raise SystemExit(f'LONG_STORY_ROUTER exhausted providers: {last}')

if __name__ == '__main__':
    raise SystemExit(main())
