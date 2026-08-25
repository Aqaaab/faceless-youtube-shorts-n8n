#!/usr/bin/env python3
from __future__ import annotations
import ast, json, re, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ERRORS=[]

def fail(msg): ERRORS.append(msg)

def main():
    py_files=sorted((ROOT/'scripts').glob('*.py'))
    for path in py_files:
        try:
            ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
            compile(path.read_text(encoding='utf-8'),str(path),'exec')
        except Exception as e: fail(f'Python syntax: {path}: {e}')
    for path in sorted(ROOT.glob('**/*.json')):
        if any(part in {'.git','data'} for part in path.parts): continue
        try: json.loads(path.read_text(encoding='utf-8'))
        except Exception as e: fail(f'JSON: {path}: {e}')
    for path in sorted(ROOT.glob('**/*.sh')):
        if '.git' in path.parts: continue
        p=subprocess.run(['bash','-n',str(path)],capture_output=True,text=True)
        if p.returncode: fail(f'Shell syntax: {path}: {p.stderr.strip()}')
    required=['scripts/generate_job.py','scripts/patent_story_engine.py','scripts/viral_engine.py','scripts/daily_content_orchestrator.py','scripts/youtube_trend_scanner.py','scripts/visual_candidate_select.py','scripts/visual_qa.py','scripts/final_feature_qa.py','scripts/create_thumbnail.py','scripts/upload_youtube.py']
    for rel in required:
        if not (ROOT/rel).is_file(): fail(f'Missing required file: {rel}')
    refs=set()
    for path in ROOT.glob('.github/workflows/*.yml'):
        text=path.read_text(encoding='utf-8')
        refs.update(re.findall(r'(?:python\s+|bash\s+|run:\s*)?(scripts/[A-Za-z0-9_.-]+\.(?:py|sh))',text))
    for rel in sorted(refs):
        if not (ROOT/rel).is_file(): fail(f'Workflow references missing file: {rel}')
    if ERRORS:
        print('\n'.join('ERROR: '+x for x in ERRORS)); return 1
    print(f'REPOSITORY_AUDIT=PASS python={len(py_files)} json_checked={len(list(ROOT.glob("**/*.json")))} shell_checked={len(list(ROOT.glob("**/*.sh")))}')
    return 0

if __name__=='__main__': raise SystemExit(main())
