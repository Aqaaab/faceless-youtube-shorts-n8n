#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS = []


def fail(msg):
    ERRORS.append(msg)


def main():
    py_files = sorted((ROOT / 'scripts').glob('*.py'))
    for path in py_files:
        try:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        except Exception as e:
            fail(f'Python syntax: {path}: {e}')

    json_files = [p for p in ROOT.glob('**/*.json') if not any(part in {'.git', 'data'} for part in p.parts)]
    for path in sorted(json_files):
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            fail(f'JSON: {path}: {e}')

    shell_files = [p for p in ROOT.glob('**/*.sh') if '.git' not in p.parts]
    for path in sorted(shell_files):
        p = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True)
        if p.returncode:
            fail(f'Shell syntax: {path}: {p.stderr.strip()}')

    required = [
        'scripts/generate_job.py',
        'scripts/patent_story_engine.py',
        'scripts/viral_engine.py',
        'scripts/daily_content_orchestrator.py',
        'scripts/youtube_trend_scanner.py',
        'scripts/visual_candidate_select.py',
        'scripts/visual_qa.py',
        'scripts/final_feature_qa.py',
        'scripts/create_thumbnail.py',
        'scripts/upload_youtube.py',
        'scripts/production_contract_audit.py',
        'scripts/odysseus_gateway.py',
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            fail(f'Missing required file: {rel}')

    workflow_files = sorted(ROOT.glob('.github/workflows/*.yml')) + sorted(ROOT.glob('.github/workflows/*.yaml'))
    refs = set()
    for path in workflow_files:
        text = path.read_text(encoding='utf-8')
        try:
            import yaml
            yaml.safe_load(text)
        except ImportError:
            fail('PyYAML is required for workflow parsing')
        except Exception as e:
            fail(f'Workflow YAML: {path}: {e}')
        refs.update(re.findall(r'(?:python\s+|bash\s+|run:\s*)?(scripts/[A-Za-z0-9_.-]+\.(?:py|sh))', text))

    for rel in sorted(refs):
        if not (ROOT / rel).is_file():
            fail(f'Workflow references missing file: {rel}')

    contract = ROOT / 'config/production-contract.json'
    if contract.is_file():
        try:
            c = json.loads(contract.read_text(encoding='utf-8'))
            canonical = c['canonical_workflow']
            if not (ROOT / canonical).is_file():
                fail(f'Canonical workflow missing: {canonical}')
            for rel in c.get('legacy', {}).get('forbidden_workflow_files', []):
                if (ROOT / rel).exists():
                    fail(f'Legacy workflow still present: {rel}')
        except Exception as e:
            fail(f'Production contract integrity: {e}')

    if ERRORS:
        print('\n'.join('ERROR: ' + x for x in ERRORS))
        return 1

    print(
        'REPOSITORY_AUDIT=PASS '
        f'python={len(py_files)} json_checked={len(json_files)} '
        f'shell_checked={len(shell_files)} workflows={len(workflow_files)} '
        f'workflow_refs={len(refs)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
