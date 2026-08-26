#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))

def main():
    scene_file=RUN_DIR/'scene_intelligence.json'
    if not scene_file.is_file(): raise SystemExit('VISUAL_INPUT_MISSING')
    data=json.loads(scene_file.read_text(encoding='utf-8'))
    scenes=data.get('scenes',[])
    manifest=RUN_DIR/'visual_asset_manifest.json'
    assets=[]
    if manifest.is_file():
        try: assets=json.loads(manifest.read_text(encoding='utf-8')).get('assets',[])
        except Exception: assets=[]
    by_scene={int(a.get('scene_number',-1)):a for a in assets if isinstance(a,dict)}
    results=[]
    for s in scenes:
        n=int(s['scene_number']); a=by_scene.get(n,{})
        path=a.get('path') or a.get('file')
        exists=bool(path and Path(path).is_file())
        duplicate=bool(a.get('duplicate',False))
        semantic=float(a.get('semantic_score',1.0 if exists else 0.0))
        quality=float(a.get('quality_score',1.0 if exists else 0.0))
        score=round(0.6*semantic+0.4*quality,3)
        results.append({'scene_number':n,'path':path,'semantic_score':semantic,'quality_score':quality,'relevance_score':score,'usable':exists and not duplicate and score>=0.70})
    bad=[x['scene_number'] for x in results if not x['usable']]
    payload={'stage':'visual_asset_validator','scene_count':len(results),'usable_count':len(results)-len(bad),'failed_scenes':bad,'assets':results,'provenance_required':True}
    (RUN_DIR/'visual_qa.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if bad and os.environ.get('REQUIRE_VISUAL_ASSET_MANIFEST','false').lower()=='true': raise SystemExit('VISUAL_ASSET_QA_FAILED:'+','.join(map(str,bad)))
    print(f"VISUAL_ASSET_QA=PASS scenes={len(results)} failed={len(bad)}")
if __name__=='__main__': main()
