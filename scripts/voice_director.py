#!/usr/bin/env python3
from __future__ import annotations
import json,os
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); JOB=RUN_DIR/'job.json'

def main():
    if not JOB.exists(): raise SystemExit('job.json missing')
    # Production content is already generated and validated by Aqaaab AI Router.
    # Keep this optional post-processor disabled by default so render never bypasses
    # the central router through direct OpenRouter/Gemini/Groq/Together calls.
    router_only=os.getenv('AI_ROUTER_ONLY','true').strip().lower()=='true'
    if router_only:
        d=json.loads(JOB.read_text(encoding='utf-8'))
        provider=str(d.get('provider','')).strip()
        if not provider or provider in {'deterministic-fallback','baseline-fallback'}:
            raise SystemExit(f'invalid upstream AI provider: {provider!r}')
        print(f'Voice Director SKIP: Aqaaab AI Router output preserved provider={provider}')
        return 0
    print('Voice Director post-processing is disabled for production safety.')
    return 0

if __name__=='__main__': raise SystemExit(main())
