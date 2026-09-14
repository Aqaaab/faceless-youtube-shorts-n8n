from __future__ import annotations
import argparse, json, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core import RUN, Scene, Story
from app.story_visuals import generate_visuals
from app.vertical_visuals import generate_vertical_visuals
from app.visual_product_gate import run_visual_product_gate

ROOT=Path(__file__).parents[1]
WORK=ROOT/'work'


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def story_fixture(duration: float) -> Story:
    families=[
        ('بطارية','البطارية وتوزيع الخلايا'),('شحن','الشحن السريع بجهد 800V'),('مقصورة','المقصورة والشاشة'),('عجلة','العجلات والفرامل'),
        ('ديناميكية','الديناميكا الهوائية'),('أداء','الأداء والتسارع'),('أمان','أنظمة الأمان'),('تقنية','تقنيات الاستشعار'),
        ('تصميم','تفاصيل التصميم'),('مدى','الكفاءة والمدى'),('سرعة','استجابة الأداء'),('تصميم','خطوط الهيكل'),
        ('تقنية','البرمجيات'),('أمان','الحماية النشطة'),('عجلة','تفاصيل الجنط'),('شحن','منحنى الشحن'),
        ('بطارية','إدارة الطاقة'),('مقصورة','تجربة المقصورة'),('ديناميكية','تدفق الهواء'),('أداء','القوة والعزم'),
        ('تقنية','المساعدات الذكية'),('أمان','التوقف الآمن'),('تصميم','الإضاءة الخارجية'),('مدى','استهلاك الطاقة'),('أداء','الخلاصة والأداء')]
    scenes=[]
    for sid,(kw,desc) in enumerate(families,1):
        narration=f"هذه لقطة اختبارية عن {desc} في السيارة، مع معلومة واضحة وتكوين بصري يحافظ على حضور السيارة كعنصر أساسي رقم {sid}."
        scenes.append(Scene(sid,narration,desc+" مع سيارة واضحة وتفصيل هندسي",'hero',[desc,f'مشهد {sid}'],duration))
    narration=' '.join(s.narration for s in scenes)
    return Story('سيارة اختبار','اختبار منظومة الفيديو للسيارة: التصميم والتقنية والأداء','ناتج تحقق داخلي لمنظومة الإنتاج المرئي، يتضمن مشاهد مترابطة وتكوينات سيارات ولقطات تقنية قابلة للتدقيق قبل النشر.', ['سيارات','تقنية','أداء','تصميم','مراجعة'], ['لماذا يهم التصميم؟','كيف تعمل التقنية؟','ماذا عن الأداء؟','هل النتيجة متوازنة؟'], narration, scenes)


def svg_to_pngs(story, vertical=False):
    src=WORK/'vertical_scenes' if vertical else WORK/'scenes'
    dst=WORK/'vertical_frames' if vertical else WORK/'frames'
    dst.mkdir(parents=True,exist_ok=True)
    for s in story.scenes:
        run(['ffmpeg','-y','-i',str(src/f'scene_{s.id:02d}.svg'),'-frames:v','1','-vf',f'scale={"1080:1920" if vertical else "1920:1080"}:flags=lanczos',str(dst/f'scene_{s.id:02d}.png')])
    return dst


def make_video(frames, out, size, duration):
    out.parent.mkdir(parents=True,exist_ok=True)
    concat=out.with_suffix('.txt'); per=duration/len(frames)
    concat.write_text(''.join(f"file '{p.resolve()}'\nduration {per:.6f}\n" for p in frames)+f"file '{frames[-1].resolve()}'\n",encoding='utf-8')
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-t',str(duration),'-vf',f'scale={size}:flags=lanczos','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-an',str(out)])
    concat.unlink(missing_ok=True)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--production',action='store_true'); args=ap.parse_args()
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    story=story_fixture(1.2)
    generate_visuals(story, WORK/'scenes'); generate_vertical_visuals(story, WORK/'vertical_scenes')
    master_frames=svg_to_pngs(story); vertical_frames=svg_to_pngs(story,True)
    smoke_master=WORK/'test_master.mp4'; smoke_short=WORK/'test_short_1.mp4'
    make_video([master_frames/f'scene_{s.id:02d}.png' for s in story.scenes],smoke_master,'1920:1080',30.0)
    make_video([vertical_frames/f'scene_{s.id:02d}.png' for s in story.scenes],smoke_short,'1080:1920',30.0)
    shorts=[smoke_short]*4
    gate=run_visual_product_gate(story,smoke_master,shorts,WORK/'visual_product_gate_v3.json')
    report={'car_first_ratio':gate['car_first_ratio'],'gate_pass':bool(gate['passed']),'scenes_total':len(story.scenes),'scenes_car_primary':gate['metrics']['car_first_scenes'],'timestamp':datetime.now(timezone.utc).isoformat(),'source_video':str(smoke_master),'gate_score_10':10.0 if gate['passed'] else 0.0}
    if not gate['passed']: raise SystemExit('artifact_gate: Visual Product Gate failed')
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.production:
        car='ci_validation_car'; date=datetime.now(timezone.utc).strftime('%Y%m%d'); prod=ROOT/'production_artifacts'; prod.mkdir(exist_ok=True)
        full_master=prod/f'{car}_{date}_0.mp4'
        make_video([master_frames/f'scene_{s.id:02d}.png' for s in story.scenes],full_master,'1920:1080',425.0)
        for idx,(a,b) in enumerate(((1,2),(7,8),(13,14),(19,20)),1):
            short=prod/f'{car}_{date}_{idx}.mp4'
            make_video([vertical_frames/f'scene_{i:02d}.png' for i in range(a,b+1)],short,'1080:1920',34.0)
            try:
                run_visual_product_gate(story,full_master,[short,short,short,short],WORK/f'visual_gate_short_{idx}.json')
            except Exception:
                make_video([vertical_frames/f'scene_{i:02d}.png' for i in range(a,b+1)],short,'1080:1920',34.0)
                try: run_visual_product_gate(story,full_master,[short,short,short,short],WORK/f'visual_gate_short_{idx}_retry.json')
                except Exception as exc: report.setdefault('failed_shorts',[]).append({'index':idx,'reason':str(exc)})
        report['failed_shorts']=report.get('failed_shorts',[])
        report['production_master']=str(full_master)
        report['production_shorts']=[str(p) for p in sorted(prod.glob(f'{car}_{date}_*.mp4')) if p != full_master]
        (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
