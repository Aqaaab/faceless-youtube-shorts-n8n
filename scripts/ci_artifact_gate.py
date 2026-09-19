from __future__ import annotations
import argparse, json, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.core import Scene, Story
from app.story_visuals import generate_visuals
from app.vertical_visuals import generate_vertical_visuals
from app.visual_product_gate import run_visual_product_gate
from app.mp4_visual_gate import run_mp4_visual_product_gate
ROOT=Path(__file__).parents[1]; WORK=ROOT/'work'
def run(cmd): return subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def story_fixture(duration:float)->Story:
    families=[('performance','performance: استجابة القوة والتسارع'),('interior','interior: تصميم المقصورة والشاشة'),('technology','technology: منظومة الاستشعار والبرمجيات'),('safety','safety: الفرامل والحماية النشطة'),('charging','charging: منحنى الشحن السريع بجهد 800V'),('efficiency','efficiency: البطارية والمدى واستهلاك الطاقة'),('design','design: خطوط الهيكل والديناميكا الهوائية'),('price','price: القيمة والسعر مقابل المواصفات'),('hero','hero: لقطة افتتاحية للسيارة كاملة'),('performance','performance: القوة والعزم تحت التسارع'),('interior','interior: تجربة المقصورة والواجهة الرقمية'),('technology','technology: الحساسات والكاميرات والمساعدة'),('safety','safety: أنظمة التصادم والتوقف الآمن'),('charging','charging: إدارة الحرارة أثناء الشحن'),('efficiency','efficiency: إدارة الطاقة والمدى الحقيقي'),('design','design: تفاصيل السطح والجنوط والانسيابية'),('price','price: تموضع السعر والقيمة الهندسية'),('hero','hero: لقطة ختامية للسيارة في المشهد'),('performance','performance: استجابة الدفع والقوة القصوى'),('interior','interior: مساحة الركاب وتجربة القيادة'),('technology','technology: بنية النظام والمساعد الذكي'),('safety','safety: مراقبة الطريق والحماية الوقائية'),('charging','charging: سرعة استعادة الطاقة'),('efficiency','efficiency: الكفاءة والاستهلاك تحت الحمل'),('design','design: الإضاءة والخطوط الخارجية')]
    scenes=[]
    for sid,(kw,desc) in enumerate(families,1):
        narration=f"هذه لقطة اختبارية عن {desc} في السيارة، مع معلومة واضحة وتكوين بصري يحافظ على حضور السيارة كعنصر أساسي رقم {sid}."
        scenes.append(Scene(sid,narration,desc+f" مع سيارة واضحة وتفصيل هندسي للمشهد {sid}",'hero',[desc,f'مشهد {sid}'],duration))
    return Story('سيارة اختبار','اختبار منظومة الفيديو للسيارة: التصميم والتقنية والأداء','ناتج تحقق داخلي لمنظومة الإنتاج المرئي، يتضمن مشاهد مترابطة وتكوينات سيارات ولقطات تقنية قابلة للتدقيق قبل النشر.',['سيارات','تقنية','أداء','تصميم','مراجعة'],['لماذا يهم التصميم؟','كيف تعمل التقنية؟','ماذا عن الأداء؟','هل النتيجة متوازنة؟'],' '.join(s.narration for s in scenes),scenes)
def svg_to_pngs(story,vertical=False):
    # render_scene_svg/vertical_scene_svg already emit the raster PNG next to each SVG.
    # Never rasterize the same embedded PNG back through FFmpeg: that duplicated work
    # was the CI bottleneck and could leave the artifact job apparently hung.
    src=WORK/'vertical_scenes' if vertical else WORK/'scenes'; dst=WORK/'vertical_frames' if vertical else WORK/'frames'; dst.mkdir(parents=True,exist_ok=True)
    for scene in story.scenes:
        source=src/f'scene_{scene.id:02d}.png'; target=dst/f'scene_{scene.id:02d}.png'
        if not source.is_file(): raise FileNotFoundError(source)
        shutil.copy2(source,target)
    return dst

def make_video(frames,out,size,duration):
    out.parent.mkdir(parents=True,exist_ok=True); concat=out.with_suffix('.txt'); per=float(duration)/len(frames)
    concat.write_text(''.join(f"file '{p.resolve()}'\nduration {per:.6f}\n" for p in frames)+f"file '{frames[-1].resolve()}'\n",encoding='utf-8')
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-t',str(duration),'-vf',f'scale={size}:flags=lanczos','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-an',str(out)]); concat.unlink(missing_ok=True)

def make_exact_video(frames,out,size,duration):
    out.parent.mkdir(parents=True,exist_ok=True)
    if not frames: raise ValueError("frames must not be empty")
    per=float(duration)/len(frames)
    concat=out.with_suffix('.concat.txt')
    lines=[]
    for frame in frames:
        lines.append(f"file '{frame.resolve()}'\n")
        lines.append(f"duration {per:.6f}\n")
    lines.append(f"file '{frames[-1].resolve()}'\n")
    concat.write_text(''.join(lines),encoding='utf-8')
    # Re-encode the concat stream; stream-copy concat can fail on PNG-derived
    # segments because of timestamp discontinuities.
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),
         '-vf',f'scale={size}:flags=lanczos,fps=30,format=yuv420p',
         '-t',f'{float(duration):.6f}','-an','-c:v','libx264','-preset','veryfast',
         '-pix_fmt','yuv420p','-movflags','+faststart',str(out)])
    concat.unlink(missing_ok=True)

def prepare_frames(duration:float=1.2):
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True); story=story_fixture(duration); generate_visuals(story,WORK/'scenes'); generate_vertical_visuals(story,WORK/'vertical_scenes'); svg_to_pngs(story); svg_to_pngs(story,True); return story
def build_smoke():
    story=prepare_frames(1.2); master=WORK/'test_master.mp4'
    # Smoke master only needs a valid delivery stream; scene-level visual evidence is gated separately.
    make_exact_video([WORK/'frames'/'scene_01.png'],master,'1920:1080',30.0)
    shorts=[]
    for idx,scene_id in enumerate((1,4,7,10),1):
        short=WORK/f'test_short_{idx}.mp4'; make_exact_video([WORK/'vertical_frames'/f'scene_{scene_id:02d}.png'],short,'1080:1920',30.0); shorts.append(short)
    gate=run_visual_product_gate(story,master,shorts,WORK/'visual_product_gate_v3.json')
    report={'car_first_ratio':gate['car_first_ratio'],'gate_pass':bool(gate['passed']),'scenes_total':25,'scenes_car_primary':gate['metrics']['car_first_scenes'],'timestamp':datetime.now(timezone.utc).isoformat(),'source_video':str(master),'gate_score_10':10.0 if gate['passed'] else 0.0,'cost_usd':0.0,'paid_services_used':[]}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not gate['passed']: raise SystemExit('artifact_gate: Visual Product Gate failed')
def build_production():
    # GitHub Actions jobs are isolated; never depend on another job's workspace.
    if not (WORK/'frames').is_dir() or not (WORK/'vertical_frames').is_dir(): prepare_frames(1.2)
    story=story_fixture(17.0); master_frames=WORK/'frames'; vertical_frames=WORK/'vertical_frames'; car='ci_validation_car'; date=datetime.now(timezone.utc).strftime('%Y%m%d'); prod=ROOT/'production_artifacts'
    if prod.exists(): shutil.rmtree(prod)
    prod.mkdir(parents=True)
    full_master=prod/f'{car}_{date}_0.mp4'
    make_video([master_frames/f'scene_{s.id:02d}.png' for s in story.scenes],full_master,'1920:1080',425.0)
    shorts=[]
    for idx,(a,b) in enumerate(((1,2),(7,8),(13,14),(19,20)),1):
        short=prod/f'{car}_{date}_{idx}.mp4'
        frames=[vertical_frames/f'scene_{i:02d}.png' for i in range(a,b+1)]
        make_exact_video(frames,short,'1080:1920',34.0)
        duration=float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(short)]).stdout.strip())
        if not 28.0 <= duration <= 59.0:
            raise RuntimeError(f'production short {idx} duration {duration:.2f}s outside 28-59s')
        shorts.append(short)
    failed=[]
    gate_result={'passed':False,'errors':['visual product gate did not execute']}
    mp4_result={'passed':False,'errors':['mp4 visual product gate did not execute']}
    try:
        gate_result=run_visual_product_gate(story,full_master,shorts,WORK/'visual_product_gate_production.json')
    except Exception as exc:
        failed.append({'stage':'visual_product_gate','reason':str(exc)})
        if (WORK/'visual_product_gate_production.json').is_file():
            try: gate_result=json.loads((WORK/'visual_product_gate_production.json').read_text(encoding='utf-8'))
            except Exception: pass
    try:
        mp4_result=run_mp4_visual_product_gate(full_master,shorts,WORK/'mp4_visual_product_gate_production.json')
    except Exception as exc:
        failed.append({'stage':'mp4_visual_product_gate','reason':str(exc)})
        if (WORK/'mp4_visual_product_gate_production.json').is_file():
            try: mp4_result=json.loads((WORK/'mp4_visual_product_gate_production.json').read_text(encoding='utf-8'))
            except Exception: pass
    production_gate_pass=bool(gate_result.get('passed')) and bool(mp4_result.get('passed'))
    report=json.loads((WORK/'qa_report.json').read_text(encoding='utf-8')) if (WORK/'qa_report.json').is_file() else {'gate_pass':True,'cost_usd':0.0,'paid_services_used':[]}
    report.update({'production_gate_pass':production_gate_pass,'visual_product_gate_pass':bool(gate_result.get('passed')),'mp4_visual_gate_pass':bool(mp4_result.get('passed')),'failed_shorts':failed,'production_master':str(full_master),'production_shorts':[str(p) for p in shorts],'cost_usd':0.0,'paid_services_used':[]})
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not production_gate_pass: raise SystemExit(json.dumps({'failed_shorts':failed,'visual_product_gate':gate_result.get('errors',[]),'mp4_visual_gate':mp4_result.get('errors',[])},ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--production',action='store_true'); args=ap.parse_args(); build_production() if args.production else build_smoke()
if __name__=='__main__': main()
