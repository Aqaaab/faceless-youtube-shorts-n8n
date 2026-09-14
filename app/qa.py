from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from . import artifact_gate as _ag
from .artifact_gate import qa as _legacy_qa
from .visual_product_gate import run_visual_product_gate


def _flexible_subtitle_gate(root:Path, shorts:list[Path]):
    srt=root/'arabic.srt'
    if not srt.is_file(): return False,'subtitle file missing'
    text=srt.read_text(encoding='utf-8')
    cues=len(re.findall(r'^\d+\s*$',text,re.M))
    arabic=sum(1 for c in text if '\u0600'<=c<='\u06ff')
    if cues<25 or arabic<20: return False,f'master subtitles insufficient: cues={cues}, arabic_chars={arabic}'
    try:
        marker=json.loads((root/'subtitle_burn.json').read_text(encoding='utf-8')); final=root/'master_final.mp4'
        if marker.get('burned') is not True or marker.get('output')!=final.name: return False,'master subtitle marker invalid'
        if marker.get('output_sha256')!=hashlib.sha256(final.read_bytes()).hexdigest(): return False,'master subtitle hash mismatch'
        if marker.get('opaque_box') is not False or marker.get('max_lines')!=2 or marker.get('safe_zone')!='bottom': return False,'master subtitle layout contract failed'
        records=json.loads((root/'short_subtitles_burn.json').read_text(encoding='utf-8')).get('shorts',[])
        if len(records)!=4: return False,'expected four Short subtitle records'
        for i,(record,path) in enumerate(zip(records,shorts),1):
            if record.get('burned') is not True or record.get('opaque_box') is not False: return False,f'Short {i} subtitle contract failed'
            st=Path(record.get('srt',''))
            if not st.is_file(): return False,f'Short {i} SRT missing'
            if len(re.findall(r'^\d+\s*$',st.read_text(encoding='utf-8'),re.M))<4: return False,f'Short {i} has too few subtitle cues'
        return True,'multi-cue Arabic subtitle evidence verified'
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc: return False,f'subtitle evidence invalid: {exc}'


def qa(story,master,shorts,report=None):
    # Replace the old fixed 25/2-cue contract before running the complete legacy QA suite.
    _ag._subtitle_gate=_flexible_subtitle_gate
    result=_legacy_qa(story,master,shorts,report) if report is not None else _legacy_qa(story,master,shorts)
    visual=run_visual_product_gate(story,master,shorts)
    result['visual_product_gate_v3']=visual
    if report is not None: report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

__all__=['qa']
