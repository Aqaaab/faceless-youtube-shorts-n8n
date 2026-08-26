#!/usr/bin/env python3
from __future__ import annotations
import json, os, statistics
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))
LEARNING_DIR=Path(os.environ.get('LEARNING_DIR','learning'))

def main():
    LEARNING_DIR.mkdir(parents=True,exist_ok=True)
    source=RUN_DIR/'analytics_metrics.json'
    metrics=json.loads(source.read_text(encoding='utf-8')) if source.is_file() else {}
    hooks=metrics.get('hooks',[])
    rows=[]
    for h in hooks:
        try:
            rows.append({'hook':h.get('hook',''),'ctr':float(h.get('ctr',0)),'retention':float(h.get('retention',0)),'views':int(h.get('views',0))})
        except Exception: continue
    avg_ctr=statistics.mean([x['ctr'] for x in rows]) if rows else 0.0
    avg_ret=statistics.mean([x['retention'] for x in rows]) if rows else 0.0
    best=max(rows,key=lambda x:(x['retention'],x['ctr'])) if rows else None
    model={'schema_version':'1.0','updated_from':'analytics_metrics.json','sample_count':len(rows),'average_ctr':round(avg_ctr,4),'average_retention':round(avg_ret,4),'best_hook':best,'next_topic_bias': 'retain_patterns' if best else 'explore'}
    (LEARNING_DIR/'production_learning.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (RUN_DIR/'analytics_learning.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"ANALYTICS_LEARNING=PASS samples={len(rows)} mode={model['next_topic_bias']}")
if __name__=='__main__': main()
