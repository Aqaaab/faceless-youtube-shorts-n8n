#!/usr/bin/env python3
"""Validate repository structure against the single production contract."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'config/production-contract.json'
ROUTER=ROOT/'config/ai-router.json'
SLOTS=ROOT/'config/long-story-slots.json'
PLAN=ROOT/'config/provider-activation-plan.json'
MESH=ROOT/'config/provider-mesh.json'
DAILY=ROOT/'.github/workflows/daily-production.yml'


def main() -> int:
    c=json.loads(CONTRACT.read_text())
    r=json.loads(ROUTER.read_text())
    s=json.loads(SLOTS.read_text())
    p=json.loads(PLAN.read_text())
    m=json.loads(MESH.read_text())
    assert c['canonical_workflow']=='.github/workflows/daily-production.yml'
    assert DAILY.is_file()
    assert not any((ROOT/x).exists() for x in c['legacy']['forbidden_workflow_files'])
    daily=DAILY.read_text()
    assert all(x not in daily for x in c['legacy']['forbidden_artifact_prefixes'])
    prod=c['production']; route=c['routing']
    assert prod['long_video_count']==1
    assert prod['long_duration_seconds']=={'min':420,'max':900}
    assert prod['short_count']==4
    assert prod['short_resolution']==[1080,1920]
    assert prod['short_video_codec']=='h264' and prod['short_fps']==30
    assert r['free_only'] is route['free_only'] and r['fail_closed'] is route['fail_closed']
    t=r['tasks']['long_story']
    assert t['mode']=='fixed_slots' and t['slot_count']==route['fixed_slots'] and t['slot_scene_count']==route['scenes_per_slot']
    assert [ [x['start_scene'],x['end_scene']] for x in s['slots'] ] == route['slot_ranges']
    assert s['rules']['never_skip_failed_slot'] is route['failed_slot_must_not_skip']
    assert all(all(k in v and v[k] for k in ('primary','backup_1','backup_2')) for v in m['tasks'].values())
    assert len(p['providers']) <= 100
    assert (ROOT/'scripts/compatible_provider_pool.py').is_file()
    print('PRODUCTION_CONTRACT=PASS')
    print('CANONICAL_WORKFLOW=PASS')
    print('ROUTING_CONTRACT=PASS')
    print('FIXED_SLOTS_CONTRACT=PASS')
    print('ARTIFACT_CONTRACT=PASS')
    print('LEGACY_CONTRACT=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
