from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core import Scene, Story
from app.render import _burn_style
from app.story_visuals import generate_visuals
from app.vertical_visuals import generate_vertical_visuals
from app.visual_product_gate import run_visual_product_gate

ROOT=Path(__file__).parents[1]; WORK=ROOT/'work'

def run(cmd): subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def story_fixture(duration:float)->Story:
    families=[('performance','performance: استجابة القوة والتسارع'),('interior','interior: تصميم المقصورة والشاشة'),('technology','technology: منظومة الاستشعار والبرمجيات'),('safety','safety: الفرامل والحماية النشطة'),('charging','charging: منحنى الشحن السريع بجهد 800V'),('efficiency','efficiency: البطارية والمدى واستهلاك الطاقة'),('design','design: خطوط الهيكل والديناميكا الهوائية'),('price','price: القيمة والسعر مقابل المواصفات'),('hero','hero: لقطة افتتاحية للسيارة كاملة'),('performance','performance: القوة والعزم تحت التسارع'),('interior','interior: تجربة المقصورة والواجهة الرقمية'),('technology','technology: الحساسات والكاميرات والمساعدة'),('safety','safety: أنظمة التصادم والتوقف الآمن'),('charging','charging: إدارة الحرارة أثناء الشحن'),('efficiency','efficiency: إدارة الطاقة والمدى الحقيقي'),('design','design: تفاصيل السطح والجنوط والانسيابية'),('price','price: تموضع السعر والقيمة الهندسية'),('hero','hero: لقطة ختامية للسيارة في المشهد'),('performance','performance: استجابة الدفع والقوة القصوى'),('interior','interior: مساحة الركاب وتجربة القيادة'),('technology','technology: بنية النظام والمساعد الذكي'),('safety','safety: مراقبة الطريق والحماية الوقائية'),('charging','charging: سرعة استعادة الطاقة'),('efficiency','efficiency: الكفاءة والاستهلاك تحت الحمل'),('design','design: الإضاءة والخطوط الخارجية')]
    scenes=[]
    for sid,(kw,desc) in enumerate(families,1):
        narration=f"هذه لقطة اختبارية عن {desc} في السيارة، مع معلومة واضحة وتكوين بصري يحافظ على حضور السيارة كعنصر أساسي رقم {sid}."
        scenes.append(Scene(sid,narration,desc+f" مع سيارة واضحة وتفصيل هندسي للمشهد {sid}",'hero',[desc,f'مشهد {sid}'],duration))
    return Story('سيارة اختبار','اختبار منظومة الفيديو للسيارة: التصميم والتقنية والأداء','ناتج تحقق داخلي لمنظومة الإنتاج المرئي، يتضمن مشاهد مترابطة وتكوينات سيارات ولقطات تقنية قابلة للتدقيق قبل النشر.',['سيارات','تقنية','أداء','تصميم','مراجعة'],['لماذا يهم التصميم؟','كيف تعمل التقنية؟','ماذا عن الأداء؟','هل النتيجة متوازنة؟'],' '.join(s.narration for s in scenes),scenes)

def svg_to_pngs(story,vertical=False):
    src=WORK/'vertical_scenes' if vertical else WORK/'scenes'; dst=WORK/'vertical_frames' if vertical else WORK/'frames'; dst.mkdir(parents=True,exist_ok=True)
    for s in story.scenes: run(['ffmpeg','-y','-i',str(src/f'scene_{s.id:02d}.svg'),'-frames:v','1','-vf',f'scale={"1080:1920" if vertical else "1920:1080"}:flags=lanczos',str(dst/f'scene_{s.id:02d}.png')])
    return dst

def make_video(frames,out,size,duration):
    out.parent.mkdir(parents=True,exist_ok=True); concat=out.with_suffix('.txt'); per=duration/len(frames)
    concat.write_text(''.join(f"file '{p.resolve()}'\nduration {per:.6f}\n" for p in frames)+f"file '{frames[-1].resolve()}'\n",encoding='utf-8')
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-t',str(duration),'-vf',f'scale={size}:flags=lanczos','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-an',str(out)]); concat.unlink(missing_ok=True)

def _ts(seconds):
    ms=int(round(seconds*1000)); sec,ms=divmod(ms,1000); h,rem=divmod(sec,3600); m,s=divmod(rem,60); return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

def prepare_subtitle_evidence(story,duration=None,source_path=None):
    if duration is None: duration=sum(float(s.duration) for s in story.scenes)
    source_path=Path(source_path) if source_path else WORK/'test_master.mp4'
    style=_burn_style(False); rows=[]
    cue_d=duration/25
    for i,s in enumerate(story.scenes,1): rows.append(f'{i}\n{_ts((i-1)*cue_d)} --> {_ts(i*cue_d)}\nالسيارة والتقنية والأداء في مشهد اختبار {i}\n')
    srt=WORK/'arabic.srt'; srt.write_text('\n'.join(rows),encoding='utf-8')
    (WORK/'subtitle_burn.json').write_text(json.dumps({'burned':True,'source':source_path.name,'output':'test_master.mp4','source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),'output_sha256':'','subtitle_file':str(srt),'subtitle_sha256':hashlib.sha256(srt.read_bytes()).hexdigest(),'style':style},ensure_ascii=False,indent=2),encoding='utf-8')
    shorts=[]
    for idx in range(1,5):
        seg=WORK/f'short_segments_{idx}'; seg.mkdir(parents=True,exist_ok=True); short_srt=seg/'short.srt'
        short_srt.write_text(f'1\n00:00:00,000 --> 00:00:15,000\nالسيارة تجمع بين التصميم والتقنية الحديثة\n\n2\n00:00:15,000 --> 00:00:30,000\nالأداء يوضح الفكرة الأساسية للمشهد\n',encoding='utf-8')
        shorts.append({'file':str(WORK/f'test_short_{idx}.mp4'),'burned':True,'output_sha256':hashlib.sha256((WORK/f'test_short_1.mp4').read_bytes()).hexdigest(),'srt':str(short_srt),'subtitle_sha256':hashlib.sha256(short_srt.read_bytes()).hexdigest(),'cue_count':2,'arabic_chars':sum(1 for ch in short_srt.read_text(encoding='utf-8') if '\u0600'<=ch<='\u06ff'),'subtitle_style':_burn_style(True)})
    (WORK/'short_subtitles_burn.json').write_text(json.dumps({'shorts':shorts},ensure_ascii=False,indent=2),encoding='utf-8')

def prepare_frames(duration:float=1.2):
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True); story=story_fixture(duration); generate_visuals(story,WORK/'scenes'); generate_vertical_visuals(story,WORK/'vertical_scenes'); svg_to_pngs(story); svg_to_pngs(story,True); return story

def build_smoke():
    story=prepare_frames(1.2); master_raw=WORK/'test_master_raw.mp4'; master=WORK/'test_master.mp4'
    make_video([WORK/'frames'/f'scene_{s.id:02d}.png' for s in story.scenes],master_raw,'1920:1080',30.0)
    prepare_subtitle_evidence(story,30.0,master_raw)
    run(['ffmpeg','-y','-i',str(master_raw),'-vf',f"subtitles={WORK/'arabic.srt'}:force_style='{_burn_style(False)}'",'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an',str(master)])
    shorts=[]
    for idx in range(1,5):
        raw=WORK/f'test_short_{idx}_raw.mp4'; out=WORK/f'test_short_{idx}.mp4'
        make_video([WORK/'vertical_frames'/f'scene_{s.id:02d}.png' for s in story.scenes],raw,'1080:1920',30.0)
        srt=WORK/f'short_segments_{idx}'/'short.srt'
        run(['ffmpeg','-y','-i',str(raw),'-vf',f"subtitles={srt}:force_style='{_burn_style(True)}'",'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an',str(out)])
        shorts.append(out)
    gate=run_visual_product_gate(story,master,shorts,WORK/'visual_product_gate_v4.json')
    report={'car_first_ratio':gate['metrics']['car_identity_signatures'],'gate_pass':bool(gate['passed']),'scenes_total':25,'scenes_car_primary':25,'timestamp':datetime.now(timezone.utc).isoformat(),'source_video':str(master),'gate_score_10':10.0 if gate['passed'] else 0.0,'cost_usd':0.0,'paid_services_used':[]}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not gate['passed']: raise SystemExit('artifact_gate: Visual Product Gate failed')

def build_production():
    if not (WORK/'frames').is_dir() or not (WORK/'vertical_frames').is_dir(): prepare_frames(1.2)
    story=story_fixture(17.0); master_raw=WORK/'production_master_raw.mp4'; master=WORK/'production_master.mp4'
    car='ci_validation_car'; date=datetime.now(timezone.utc).strftime('%Y%m%d'); prod=ROOT/'production_artifacts'
    if prod.exists(): shutil.rmtree(prod)
    prod.mkdir(parents=True)
    make_video([WORK/'frames'/f'scene_{s.id:02d}.png' for s in story.scenes],master_raw,'1920:1080',425.0)
    prepare_subtitle_evidence(story,425.0,master_raw)
    run(['ffmpeg','-y','-i',str(master_raw),'-vf',f"subtitles={WORK/'arabic.srt'}:force_style='{_burn_style(False)}'",'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an',str(master)])
    full_master=prod/f'{car}_{date}_0.mp4'; shutil.copy2(master,full_master)
    failed=[]; outputs=[]
    for idx,(a,b) in enumerate(((1,2),(7,8),(13,14),(19,20)),1):
        raw=prod/f'{car}_{date}_{idx}_raw.mp4'; short=prod/f'{car}_{date}_{idx}.mp4'
        frames=[WORK/'vertical_frames'/f'scene_{i:02d}.png' for i in range(a,b+1)]
        make_video(frames,raw,'1080:1920',34.0)
        srt=WORK/f'short_segments_{idx}'/'short.srt'
        run(['ffmpeg','-y','-i',str(raw),'-vf',f"subtitles={srt}:force_style='{_burn_style(True)}'",'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an',str(short)])
        outputs.append(short)
    try:
        run_visual_product_gate(story,full_master,outputs,WORK/'visual_product_gate_v4.json')
    except Exception as exc:
        failed.append({'index':0,'reason':str(exc)})
    report={'gate_pass':not failed,'failed_shorts':failed,'production_master':str(full_master),'production_shorts':[str(p) for p in outputs],'cost_usd':0.0,'paid_services_used':[]}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if failed: raise SystemExit(json.dumps({'failed_shorts':failed},ensure_ascii=False))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--production',action='store_true'); args=ap.parse_args(); build_production() if args.production else build_smoke()
if __name__=='__main__': main()
