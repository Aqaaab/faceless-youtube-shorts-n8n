from __future__ import annotations
import argparse,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
from app.core import Scene,Story
from app.story_visuals import generate_visuals
from app.vertical_visuals import generate_vertical_visuals
from app.visual_product_gate import run_visual_product_gate
from app.render import _caption_style
ROOT=Path(__file__).parents[1];WORK=ROOT/'work'

def run(cmd):subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def duration(path:Path)->float:return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],check=True,capture_output=True,text=True).stdout.strip())
def size(path:Path)->tuple[int,int]:
    raw=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',str(path)],check=True,capture_output=True,text=True).stdout.strip();w,h=raw.split('x',1);return int(w),int(h)

def story_fixture(duration_s:float)->Story:
    topics=[('performance','أداء واستجابة القوة والتسارع'),('interior','تصميم المقصورة والواجهة الرقمية'),('technology','منظومة الاستشعار والبرمجيات'),('safety','الفرامل والحماية النشطة'),('charging','منحنى الشحن واستعادة الطاقة'),('efficiency','البطارية والمدى واستهلاك الطاقة'),('design','خطوط الهيكل والديناميكا الهوائية'),('price','القيمة والسعر ضمن الفئة'),('hero','لقطة افتتاحية للسيارة كاملة')]
    layouts=['hero','technical','spec','comparison','diagram','timeline'];scenes=[]
    for sid in range(1,26):
        kw,desc=topics[(sid-1)%len(topics)];narration=f"هذه لقطة اختبارية عن {desc} في السيارة، مع معلومة واضحة وتكوين بصري يحافظ على حضور السيارة كعنصر أساسي في المشهد رقم {sid}."
        scenes.append(Scene(sid,narration,desc+f" مع سيارة واضحة وتفصيل هندسي للمشهد {sid}",layouts[(sid-1)%len(layouts)],[desc,f'مشهد {sid}'],duration_s))
    return Story('سيارة اختبار','اختبار منظومة الفيديو للسيارة: التصميم والتقنية والأداء','ناتج تحقق داخلي لمنظومة الإنتاج المرئي، يتضمن مشاهد مترابطة وتكوينات سيارات ولقطات تقنية قابلة للتدقيق قبل النشر.',['سيارات','تقنية','أداء','تصميم','مراجعة'],['لماذا يهم التصميم؟','كيف تعمل التقنية في السيارة؟','ماذا يقدم الأداء في الطريق؟','هل تتوازن القيمة مع المواصفات؟'],' '.join(s.narration for s in scenes),scenes)

def svg_to_pngs(story,vertical=False):
    src=WORK/'vertical_scenes' if vertical else WORK/'scenes';dst=WORK/'vertical_frames' if vertical else WORK/'frames';dst.mkdir(parents=True,exist_ok=True)
    for s in story.scenes:run(['ffmpeg','-y','-loglevel','error','-i',str(src/f'scene_{s.id:02d}.svg'),'-frames:v','1','-vf',f'scale={"1080:1920" if vertical else "1920:1080"}:flags=lanczos',str(dst/f'scene_{s.id:02d}.png')])
    return dst

def make_video(frames,out,size_s,duration_s):
    out.parent.mkdir(parents=True,exist_ok=True);concat=out.with_suffix('.txt');per=duration_s/len(frames)
    concat.write_text(''.join(f"file '{p.resolve()}'\nduration {per:.6f}\n" for p in frames)+f"file '{frames[-1].resolve()}'\n",encoding='utf-8')
    run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-t',str(duration_s),'-vf',f'scale={size_s}:flags=lanczos','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-an',str(out)]);concat.unlink(missing_ok=True)

def write_master_srt(story:Story):
    rows=[];t=0.0
    for i,scene in enumerate(story.scenes,1):
        end=t+float(scene.duration);text=f"المشهد {i}: {scene.visual_intent[:40]}";rows.append(f"{i}\n00:{int(t//60):02d}:{t%60:06.3f}".replace('.',',')+f" --> 00:{int(end//60):02d}:{end%60:06.3f}".replace('.',',')+f"\n{text}\n");t=end
    (WORK/'arabic.srt').write_text('\n'.join(rows),encoding='utf-8')

def write_short_srt(index:int):
    p=WORK/f'short_segments_{index}';p.mkdir(parents=True,exist_ok=True)
    (p/'short.srt').write_text('1\n00:00:00,000 --> 00:00:17,000\nهذه ترجمة عربية اختبارية واضحة وتبقى ضمن الهوامش الآمنة.\n\n2\n00:00:17,000 --> 00:00:34,000\nالمشهد الرأسي يعرض السيارة مع حركة وتفصيل هندسي واضح.\n',encoding='utf-8')

def burn(src:Path,srt:Path,out:Path,vertical:bool):
    style=_caption_style(vertical)
    run(['ffmpeg','-y','-loglevel','error','-i',str(src),'-vf',f"subtitles={srt}:force_style='{style}'",'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','copy',str(out)])

def prepare_frames(duration_s:float):
    if WORK.exists():shutil.rmtree(WORK)
    WORK.mkdir(parents=True);story=story_fixture(duration_s);generate_visuals(story,WORK/'scenes');generate_vertical_visuals(story,WORK/'vertical_scenes');svg_to_pngs(story);svg_to_pngs(story,True)
    write_master_srt(story)
    for i in range(1,5):write_short_srt(i)
    return story

def build_smoke():
    story=prepare_frames(1.2);master_raw=WORK/'master_raw.mp4';master=WORK/'test_master.mp4';pairs=((1,2),(7,8),(13,14),(19,20));raw_shorts=[];shorts=[]
    make_video([WORK/'frames'/f'scene_{s.id:02d}.png' for s in story.scenes],master_raw,'1920:1080',30.0);burn(master_raw,WORK/'arabic.srt',master,False)
    for idx,(a,b) in enumerate(pairs,1):
        raw=WORK/f'test_short_raw_{idx}.mp4';p=WORK/f'test_short_{idx}.mp4';make_video([WORK/'vertical_frames'/f'scene_{a:02d}.png',WORK/'vertical_frames'/f'scene_{b:02d}.png'],raw,'1080:1920',30.0);burn(raw,WORK/f'short_segments_{idx}'/'short.srt',p,True);raw_shorts.append(raw);shorts.append(p)
    gate=run_visual_product_gate(story,master,shorts,WORK/'visual_product_gate_v4.json')
    report={'gate_version':'v4','gate_pass':bool(gate['passed']),'scenes_total':25,'scenes_car_primary':gate['car_first_scenes'],'visual_product_gate':gate,'timestamp':datetime.now(timezone.utc).isoformat(),'source_video':str(master_raw),'burned_master':str(master),'master_duration':duration(master),'short_durations':[duration(p) for p in shorts],'short_resolutions':[list(size(p)) for p in shorts],'cost_usd':0.0,'paid_services_used':[]}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not gate['passed']:raise SystemExit('artifact_gate: Visual Product Gate failed')

def build_production():
    story=prepare_frames(17.0);master_frames=WORK/'frames';vertical_frames=WORK/'vertical_frames';car='ci_validation_car';date=datetime.now(timezone.utc).strftime('%Y%m%d');prod=ROOT/'production_artifacts';pairs=((1,2),(7,8),(13,14),(19,20))
    if prod.exists():shutil.rmtree(prod)
    prod.mkdir(parents=True);master_raw=prod/f'{car}_{date}_raw.mp4';full_master=prod/f'{car}_{date}_0.mp4';make_video([master_frames/f'scene_{s.id:02d}.png' for s in story.scenes],master_raw,'1920:1080',425.0);burn(master_raw,WORK/'arabic.srt',full_master,False);short_paths=[]
    for idx,(a,b) in enumerate(pairs,1):
        raw=prod/f'{car}_{date}_raw_{idx}.mp4';short=prod/f'{car}_{date}_{idx}.mp4';make_video([vertical_frames/f'scene_{a:02d}.png',vertical_frames/f'scene_{b:02d}.png'],raw,'1080:1920',34.0);write_short_srt(idx);burn(raw,WORK/f'short_segments_{idx}'/'short.srt',short,True);short_paths.append(short)
    gate=run_visual_product_gate(story,full_master,short_paths,WORK/'visual_product_gate_v4.json');md=duration(full_master);sd=[duration(p) for p in short_paths];res=[list(size(p)) for p in short_paths]
    if not 420.0<=md<=900.0:raise SystemExit(f'production master duration invalid: {md:.2f}s')
    if any(not 28.0<=d<=59.0 for d in sd):raise SystemExit(f'production Short duration invalid: {sd}')
    if any(r!=[1080,1920] for r in res):raise SystemExit(f'production Short resolution invalid: {res}')
    report={'gate_version':'v4','gate_pass':bool(gate['passed']),'failed_shorts':[],'production_master':str(full_master),'production_shorts':[str(p) for p in short_paths],'master_duration':md,'short_durations':sd,'short_resolutions':res,'visual_product_gate':gate,'cost_usd':0.0,'paid_services_used':[],'timestamp':datetime.now(timezone.utc).isoformat()}
    (WORK/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not gate['passed']:raise SystemExit(json.dumps({'visual_errors':gate['errors']},ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--production',action='store_true');args=ap.parse_args();build_production() if args.production else build_smoke()
if __name__=='__main__':main()
