from __future__ import annotations
import argparse, json, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.core import Scene, Story
from app.story_visuals import generate_visuals
from app.vertical_visuals import generate_vertical_visuals
from app.visual_product_gate import run_visual_product_gate, _metric, _distance
from app.mp4_visual_gate import run_mp4_visual_product_gate, _portrait_frame_ok, _raster_texture_ok
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
    out.parent.mkdir(parents=True,exist_ok=True)
    if not frames: raise ValueError("frames must not be empty")
    concat=out.with_suffix('.txt'); per=float(duration)/len(frames)
    concat.write_text(''.join(f"file '{p.resolve()}'\nduration {per:.6f}\n" for p in frames)+f"file '{frames[-1].resolve()}'\n",encoding='utf-8')
    try:
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),
             '-t',f'{float(duration):.6f}',
             '-vf',f'scale={size}:flags=lanczos,fps=30,format=yuv420p',
             '-an','-c:v','libx264','-preset','ultrafast','-crf','18',
             '-pix_fmt','yuv420p','-movflags','+faststart',str(out)])
    finally:
        concat.unlink(missing_ok=True)

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
    try:
        # Explicit CFR + finite duration makes long PNG concat renders stable on CI
        # runners and prevents timestamp drift from aborting the production fixture.
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),
             '-vf',f'scale={size}:flags=lanczos,fps=30,format=yuv420p',
             '-t',f'{float(duration):.6f}','-an','-c:v','libx264',
             '-preset','ultrafast','-crf','18','-pix_fmt','yuv420p',
             '-movflags','+faststart',str(out)])
    finally:
        concat.unlink(missing_ok=True)

def prepare_frames(duration:float=1.2):
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True); story=story_fixture(duration); generate_visuals(story,WORK/'scenes'); generate_vertical_visuals(story,WORK/'vertical_scenes'); svg_to_pngs(story); svg_to_pngs(story,True); return story

def prepare_production_frames(duration:float=1.2):
    """Render all landscape evidence, but only the portrait frames actually used by production."""
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    story=story_fixture(duration)
    generate_visuals(story,WORK/'scenes')
    # Production selection must see the complete portrait candidate pool.
    # Rendering only predetermined pairs can bias the result and hide stronger
    # disjoint Shorts elsewhere in the 25-scene story.
    generate_vertical_visuals(story,WORK/'vertical_scenes')
    svg_to_pngs(story)
    svg_to_pngs(story,True)
    return story
def build_smoke():
    story=prepare_frames(1.2); master=WORK/'test_master.mp4'
    # Smoke master only needs a valid delivery stream; scene-level visual evidence is gated separately.
    make_exact_video([WORK/'frames'/'scene_01.png'],master,'1920:1080',30.0)
    # Select four representatives from the rendered portrait evidence using the same pixel metric as the gate.
    candidates=[(scene.id,_metric(WORK/'vertical_frames'/f'scene_{scene.id:02d}.png',True)['image']) for scene in story.scenes]
    # Choose the four-image subset that maximizes the same cross-short metric
    # used by the gate. A greedy seed can get trapped just below the threshold even
    # when another valid four-scene subset has materially better separation.
    from itertools import combinations
    best_combo=None; best_key=None
    for combo in combinations(candidates,4):
        # Camera-slot diversity is a preference, never a hard failure.
        min_distance=min(_distance(x[1],y[1]) for x,y in combinations(combo,2))
        unique_slots=len({(scene_id-1)%8 for scene_id,_ in combo})
        key=(min_distance,unique_slots)
        if best_key is None or key>best_key:
            best_key=key; best_combo=combo
    if best_combo is None: raise RuntimeError("unable to select four valid smoke Shorts")
    selected=list(best_combo)
    shorts=[]
    for idx,(scene_id,_) in enumerate(selected,1):
        short=WORK/f'test_short_{idx}.mp4'; make_exact_video([WORK/'vertical_frames'/f'scene_{scene_id:02d}.png'],short,'1080:1920',30.0); shorts.append(short)
    gate=run_visual_product_gate(story,master,shorts,WORK/'visual_product_gate_v3.json')
    report={'car_first_ratio':gate['car_first_ratio'],'gate_pass':bool(gate['passed']),'scenes_total':25,'scenes_car_primary':gate['metrics']['car_first_scenes'],'timestamp':datetime.now(timezone.utc).isoformat(),'source_video':str(master),'gate_score_10':10.0 if gate['passed'] else 0.0,'cost_usd':0.0,'paid_services_used':[]}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not gate['passed']: raise SystemExit('artifact_gate: Visual Product Gate failed')
def build_production():
    # GitHub Actions jobs are isolated; never depend on another job's workspace.
    if not (WORK/'frames').is_dir() or not (WORK/'vertical_frames').is_dir():
        prepare_production_frames(1.2)
    story=story_fixture(17.0)
    master_frames=WORK/'frames'
    vertical_frames=WORK/'vertical_frames'
    car='ci_validation_car'
    date=datetime.now(timezone.utc).strftime('%Y%m%d')
    prod=ROOT/'production_artifacts'
    if prod.exists(): shutil.rmtree(prod)
    prod.mkdir(parents=True)

    full_master=prod/f'{car}_{date}_0.mp4'
    make_video([master_frames/f'scene_{s.id:02d}.png' for s in story.scenes],full_master,'1920:1080',425.0)

    # Build every valid two-scene portrait candidate (24 possible starts).
    # No fixed scene pairs are permitted in production selection.
    candidates=[]
    rejected=[]
    for start_scene in range(1, len(story.scenes)):
        pair_paths=[vertical_frames/f'scene_{i:02d}.png' for i in (start_scene,start_scene+1)]
        if not all(p.is_file() for p in pair_paths):
            rejected.append({"scene":start_scene,"pair":"portrait frame not rendered"})
            continue
        checks=[]
        valid=True
        for frame_path in pair_paths:
            fill_ok, fill_reason=_portrait_frame_ok(frame_path)
            texture_ok, texture_reason=_raster_texture_ok(full_master,frame_path)
            checks.append((frame_path.name,fill_ok,fill_reason,texture_ok,texture_reason))
            valid = valid and fill_ok and texture_ok
        if not valid:
            rejected.append({"scene":start_scene,"pair":checks})
            continue

        # Represent the actual Short by both frames, not only its first frame.
        vectors=[_metric(p,True)['image'] for p in pair_paths]
        pair_vector=[sum(v[i] for v in vectors)/len(vectors) for i in range(len(vectors[0]))]
        candidates.append((start_scene,pair_vector))

    if len(candidates)<4:
        raise RuntimeError(f"fewer than four portrait production candidates pass delivery gates: {json.dumps(rejected,ensure_ascii=False)}")

    from itertools import combinations
    best_combo=None
    best_key=None
    for combo in combinations(candidates,4):
        starts=[x[0] for x in combo]
        scene_sets=[set((s,s+1)) for s in starts]
        if any(scene_sets[i].intersection(scene_sets[j]) for i in range(4) for j in range(i+1,4)):
            continue
        min_distance=min(_distance(a[1],b[1]) for a,b in combinations(combo,2))
        # Secondary preference: spread scene positions as well as pixels.
        spread=len({s for s,_ in combo})
        key=(min_distance,spread)
        if best_key is None or key>best_key:
            best_key=key
            best_combo=combo

    if best_combo is None:
        raise RuntimeError("unable to select four disjoint production Shorts")

    selected_starts=[scene_id for scene_id,_ in best_combo]
    selected_pairs=[(scene_id,scene_id+1) for scene_id in selected_starts]
    shorts=[]
    for idx,(a,b) in enumerate(selected_pairs,1):
        short=prod/f'{car}_{date}_{idx}.mp4'
        frames=[vertical_frames/f'scene_{i:02d}.png' for i in (a,b)]
        make_exact_video(frames,short,'1080:1920',34.0)
        duration=float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(short)]).stdout.strip())
        if not 28.0<=duration<=59.0:
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
        failed.append({'stage':'mp4_visual_gate','reason':str(exc)})
        if (WORK/'mp4_visual_product_gate_production.json').is_file():
            try: mp4_result=json.loads((WORK/'mp4_visual_product_gate_production.json').read_text(encoding='utf-8'))
            except Exception: pass

    production_gate_pass=bool(gate_result.get('passed')) and bool(mp4_result.get('passed'))
    # production_render is an isolated Actions job; do not inherit or require
    # artifact_gate's qa_report.json. Build the production report from the
    # production evidence generated above.
    report={
        'car_first_ratio': gate_result.get('car_first_ratio', 0.0),
        'gate_pass': bool(gate_result.get('passed')) and bool(mp4_result.get('passed')),
        'scenes_total': len(story.scenes),
        'scenes_car_primary': gate_result.get('metrics', {}).get('car_first_scenes', 0),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'source_video': str(full_master),
        'gate_score_10': 10.0 if (gate_result.get('passed') and mp4_result.get('passed')) else 0.0,
        'cost_usd': 0.0,
        'paid_services_used': [],
    }
    report.update({
        'production_gate_pass':production_gate_pass,
        'visual_product_gate_pass':bool(gate_result.get('passed')),
        'mp4_visual_gate_pass':bool(mp4_result.get('passed')),
        'failed_shorts':failed,
        'production_master':str(full_master),
        'production_shorts':[str(p) for p in shorts],
        'production_short_selection':{
            'candidate_count':len(candidates),
            'rejected_candidates':rejected,
            'selected_starts':selected_starts,
            'selected_pairs':selected_pairs,
            'min_pixel_distance':round(best_key[0],4) if best_key else 0.0,
            'unique_camera_slots':best_key[1] if best_key else 0
        },
        'cost_usd':0.0,
        'paid_services_used':[]
    })
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not production_gate_pass:
        raise SystemExit(json.dumps({
            'failed_shorts':failed,
            'visual_product_gate':gate_result.get('errors',[]),
            'mp4_visual_gate':mp4_result.get('errors',[])
        },ensure_ascii=False))



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    if args.production:
        build_production()
    else:
        build_smoke()


if __name__ == "__main__":
    main()
