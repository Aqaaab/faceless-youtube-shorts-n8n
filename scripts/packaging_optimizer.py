#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))

def title_score(t):
    words=t.split(); s=45
    if 6<=len(words)<=14:s+=20
    if any(x in t.lower() for x in ['why','how','secret','truth','what','happened','nobody']):s+=15
    if '?' in t:s+=5
    if len(t)>90:s-=15
    return max(0,min(100,round(s,2)))

def main():
    story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    topic=str(story.get('title') or story.get('topic') or story.get('subject') or 'Untitled story').strip()
    candidates=[topic, f'What Really Happened: {topic}', f'The Truth About {topic}', f'Why {topic} Matters', f'The Part Nobody Talks About: {topic}']
    titles=sorted([{'title':x,'score':title_score(x)} for x in candidates],key=lambda x:x['score'],reverse=True)
    thumbs=[{'concept_id':f'thumb-{i+1}','concept':c,'score':max(0,90-i*7)} for i,c in enumerate(['close-up subject + conflict','before/after contrast','mystery object + reaction','high-stakes moment','clean symbolic composition'])]
    payload={'stage':'packaging_optimizer','title_candidates':titles,'winner':titles[0],'thumbnail_candidates':thumbs,'thumbnail_winner':thumbs[0]}
    (RUN_DIR/'packaging_candidates.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (RUN_DIR/'thumbnail_candidates.json').write_text(json.dumps({'stage':'thumbnail_optimizer','winner':thumbs[0],'candidates':thumbs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PACKAGING_OPTIMIZER=PASS titles=%d thumbnails=%d' % (len(titles),len(thumbs)))
if __name__=='__main__': main()
