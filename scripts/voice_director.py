#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
JOB = RUN_DIR / 'job.json'
LONG_STORY = RUN_DIR / 'long_story.json'


def main():
    # The long-form pipeline produces long_story.json. The renderer consumes job.json.
    # Bridge the two contracts without regenerating or modifying the AI output.
    if not JOB.exists() and LONG_STORY.exists():
        d = json.loads(LONG_STORY.read_text(encoding='utf-8'))
        if d.get('format') not in {'patent', 'long_form'}:
            raise SystemExit(f'invalid long-story format: {d.get("format")!r}')
        provider = str(d.get('provider', '')).strip()
        if not provider or provider in {'deterministic-fallback', 'baseline-fallback'}:
            raise SystemExit(f'invalid upstream AI provider: {provider!r}')
        JOB.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Voice Director bridge: long_story.json -> job.json provider={provider} scenes={len(d.get("scenes", []))}')
        return 0

    if not JOB.exists():
        raise SystemExit('job.json missing')

    router_only = os.getenv('AI_ROUTER_ONLY', 'true').strip().lower() == 'true'
    if router_only:
        d = json.loads(JOB.read_text(encoding='utf-8'))
        provider = str(d.get('provider', '')).strip()
        if not provider or provider in {'deterministic-fallback', 'baseline-fallback'}:
            raise SystemExit(f'invalid upstream AI provider: {provider!r}')
        print(f'Voice Director SKIP: Aqaaab AI Router output preserved provider={provider}')
        return 0

    print('Voice Director post-processing is disabled for production safety.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
