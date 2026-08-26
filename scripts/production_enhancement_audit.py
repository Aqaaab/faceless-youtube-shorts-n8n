#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    c=json.loads((ROOT/'config/production-enhancement-plan.json').read_text(encoding='utf-8'))
    assert c['status']=='implemented_and_contractual'
    for stage in c['stages']:
        assert stage['enabled'] is True, stage['id']
        ex=str(stage.get('executor',''))
        for token in ex.replace(' + ','|').split('|'):
            token=token.strip()
            if token.endswith('.py') or token.endswith('.sh'):
                assert (ROOT/token).is_file(), f'MISSING_EXECUTOR:{stage["id"]}:{token}'
    required=c['executable_stage_contract']['required_files']
    for name in required: assert (ROOT/'scripts'/name).is_file(), f'MISSING_REQUIRED_STAGE:{name}'
    orch=(ROOT/'scripts/daily_content_orchestrator.py').read_text(encoding='utf-8')
    scheduled={'youtube_analytics_learning.py'}
    for name in required:
        if name in scheduled: continue
        stem=name.rsplit('.',1)[0]
        assert stem in orch or name=='production_enhancement_audit.py', f'STAGE_NOT_WIRED:{name}'
    analytics_workflow=ROOT/'.github/workflows/youtube-analytics-learning.yml'
    assert analytics_workflow.is_file() and 'youtube_analytics_learning.py' in analytics_workflow.read_text(encoding='utf-8')

    daily_path=ROOT/'.github/workflows/daily-production.yml'
    publish_path=ROOT/'.github/workflows/publish-production.yml'
    legacy_paths=[ROOT/'.github/workflows/daily-production-v2.yml',ROOT/'.github/workflows/daily-content-contract.yml',ROOT/'.github/workflows/youtube-shorts.yml']
    assert daily_path.is_file(), 'CANONICAL_DAILY_WORKFLOW_MISSING'
    assert publish_path.is_file(), 'PUBLISH_WORKFLOW_MISSING'
    assert not any(p.exists() for p in legacy_paths), 'LEGACY_WORKFLOW_FILE_PRESENT'
    daily=daily_path.read_text(encoding='utf-8'); publish=publish_path.read_text(encoding='utf-8')
    assert 'Daily Production Pipeline' in daily
    assert 'Daily Production Pipeline v2' not in daily+publish
    assert 'daily-production-final-' in daily and 'daily-production-final-' in publish
    assert 'Daily Production Pipeline' in publish
    assert "len(p['providers']) == 11" not in daily and 'len(p["providers"]) == 11' not in daily
    assert 'len(active)==11' not in daily and 'len(active) == 11' not in daily
    qa=ROOT/'scripts/final_feature_qa.py'; assert qa.is_file()
    print('PRODUCTION_ENHANCEMENT_CONTRACT=PASS')
    print('EXECUTABLE_STAGE_COUNT='+str(len(c['stages'])))
    print('REQUIRED_STAGE_FILES='+str(len(required)))
    print('ORCHESTRATOR_STAGE_WIRING=PASS')
    print('ANALYTICS_SCHEDULE_WIRING=PASS')
    print('LEGACY_WORKFLOW_FILES_REMOVED=PASS')
    print('PUBLISH_WORKFLOW_ALIGNMENT=PASS')
    print('NO_HARDCODED_PROVIDER_COUNT=PASS')
if __name__=='__main__': raise SystemExit(main())
