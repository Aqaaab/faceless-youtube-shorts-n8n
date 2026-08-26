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
    workflow=ROOT/'.github/workflows/youtube-analytics-learning.yml'
    assert workflow.is_file() and 'youtube_analytics_learning.py' in workflow.read_text(encoding='utf-8')
    daily=(ROOT/'.github/workflows/daily-production.yml').read_text(encoding='utf-8')
    publish=(ROOT/'.github/workflows/publish-production.yml').read_text(encoding='utf-8')
    assert 'Daily Production Pipeline v2' not in daily+publish
    assert 'daily-production-v2' not in daily+publish
    assert 'Daily Production Pipeline' in publish
    assert 'daily-production-final-' in publish
    assert 'daily-production-final-${{ github.run_number }}' in daily
    qa=ROOT/'scripts/final_feature_qa.py'; assert qa.is_file()
    print('PRODUCTION_ENHANCEMENT_CONTRACT=PASS')
    print('EXECUTABLE_STAGE_COUNT='+str(len(c['stages'])))
    print('REQUIRED_STAGE_FILES='+str(len(required)))
    print('ORCHESTRATOR_STAGE_WIRING=PASS')
    print('ANALYTICS_SCHEDULE_WIRING=PASS')
    print('PUBLISH_WORKFLOW_ALIGNMENT=PASS')
if __name__=='__main__': raise SystemExit(main())
