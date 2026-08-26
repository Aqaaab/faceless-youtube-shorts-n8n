#!/usr/bin/env python3
from __future__ import annotations
import json, os, statistics
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))
LEARNING_DIR=Path(os.environ.get('LEARNING_DIR','learning'))

def main():
    LEARNING_DIR.mkdir(parents=True,exist_ok=True)
    source=RUN_DIR/'youtube_analytics.json'
    if not source.is_file():
        fallback=RUN_DIR/'analytics_metrics.json'
        metrics=json.loads(fallback.read_text(encoding='utf-8')) if fallback.is_file() else {}
        rows=metrics.get('hooks',[])
        source_name='analytics_metrics.json'
    else:
        metrics=json.loads(source.read_text(encoding='utf-8'))
        source_name='youtube_analytics.json'
        rows=[]
        for r in metrics.get('rows',[]):
            try:
                rows.append({'video':r.get('video',''),'views':int(r.get('views',0)),'watch_minutes':float(r.get('estimatedMinutesWatched',0)),'average_view_duration':float(r.get('averageViewDuration',0)),'average_view_percentage':float(r.get('averageViewPercentage',0)),'likes':int(r.get('likes',0)),'comments':int(r.get('comments',0)),'subscribers_gained':int(r.get('subscribersGained',0))})
            except Exception: continue
    avg_views=statistics.mean([x.get('views',0) for x in rows]) if rows else 0.0
    avg_ret=statistics.mean([x.get('average_view_percentage',x.get('retention',0)) for x in rows]) if rows else 0.0
    best=max(rows,key=lambda x:(x.get('average_view_percentage',0),x.get('views',0))) if rows else None
    model={'schema_version':'2.0','updated_from':source_name,'sample_count':len(rows),'average_views':round(avg_views,2),'average_retention':round(avg_ret,4),'best_video':best,'next_topic_bias':'retain_patterns' if best else 'explore','metrics_source':'youtube_analytics_api' if source_name=='youtube_analytics.json' else 'manual_or_legacy'}
    (LEARNING_DIR/'production_learning.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (RUN_DIR/'analytics_learning.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"ANALYTICS_LEARNING=PASS samples={len(rows)} source={model['metrics_source']} mode={model['next_topic_bias']}")
if __name__=='__main__': main()
