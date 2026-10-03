from __future__ import annotations
import itertools,json,re
from dataclasses import dataclass
from pathlib import Path
from PIL import Image,ImageStat
from .core import RUN,Story
from .production_contract import SHORT_MIN_SECONDS,SHORT_MAX_SECONDS,SHORT_CANDIDATE_MINIMUM,SHORT_SELECTION_MIN_PIXEL_DISTANCE

MIN_CANDIDATES=SHORT_CANDIDATE_MINIMUM; FINAL_MIN_DISTANCE=SHORT_SELECTION_MIN_PIXEL_DISTANCE

@dataclass(frozen=True)
class ShortCandidate:
    candidate_id:str; start_scene:int; end_scene:int; start_offset:float; end_trim:float; start_time:float; end_time:float; duration:float
    hook_score:float; peak_score:float; payoff_score:float; semantic_score:float; visual_score:float; topic_score:float; title:str
    @property
    def scene_ids(self): return tuple(range(self.start_scene,self.end_scene+1))
    @property
    def score(self): return self.hook_score*.22+self.peak_score*.18+self.payoff_score*.16+self.semantic_score*.16+self.visual_score*.13+self.topic_score*.08+self._duration_score()*.07
    def _duration_score(self): return max(0.0,1.0-abs(self.duration-40.0)/40.0)

HOOK=("لماذا","كيف","ما الذي","المفاجأة","أهم","فعلاً","سر","هل","لكن")
PEAK=("حصان","عزم","تسارع","سرعة","مدى","شحن","أداء","تقنية","رقم","أول","أفضل")
PAYOFF=("لذلك","النتيجة","الخلاصة","عملياً","عمليًا","في النهاية","وهنا","هذا يعني")
SEMANTIC=("تصميم","أداء","تقنية","أمان","بطارية","شحن","مدى","مقصورة","قيمة","مقارنة")

def _tokens(text): return {t for t in re.sub(r"[^\w\u0600-\u06ff]+"," ",str(text).casefold()).split() if len(t)>=3 and not t.isdigit()}
def _feature(tokens,lexicon): return min(1.0,sum(1 for item in lexicon if item in tokens)/3.0) if tokens else 0.0
def _scene_times(story):
    out={}; clock=0.0
    for scene in story.scenes: out[scene.id]=(clock,clock+float(scene.duration)); clock+=float(scene.duration)
    return out
def _scene_visual_vector(path):
    with Image.open(path).convert("RGB") as image:
        small=image.resize((16,16)); stat=ImageStat.Stat(small); pixels=list(small.getdata()); vector=[v/255.0 for v in stat.mean]
        for channel in range(3): vector.extend(pixel[channel]/255.0 for pixel in pixels[::4])
        return vector
def _distance(a,b): return 0.0 if len(a)!=len(b) else sum(abs(x-y) for x,y in zip(a,b))/len(a)
def _candidate_vector(candidate,vectors):
    vals=[vectors[sid] for sid in candidate.scene_ids if sid in vectors]
    return [sum(row[i] for row in vals)/len(vals) for i in range(len(vals[0]))] if vals else []
def _title(story,start,end):
    seed=re.sub(r"\s+"," ",story.scenes[start-1].narration).strip()[:54].rstrip("،,. ")
    return f"{seed} — {start:02d}-{end:02d}"[:80].strip()

def build_candidates(story,visual_dir):
    times=_scene_times(story); scene_map={s.id:s for s in story.scenes}; vectors={}
    for sid in scene_map:
        frame=visual_dir/f"scene_{sid:02d}.png"
        if frame.is_file():
            try: vectors[sid]=_scene_visual_vector(frame)
            except OSError: pass
    candidates=[]; variants=(0.0,1.5,3.0)
    for start in range(1,len(story.scenes)):
        end=start+1
        base_start,_=times[start]; _,base_end=times[end]
        for start_offset in variants:
            for end_trim in variants:
                start_time=base_start+start_offset; end_time=base_end-end_trim; duration=end_time-start_time
                if not SHORT_MIN_SECONDS<=duration<=SHORT_MAX_SECONDS: continue
                block=[scene_map[sid] for sid in (start,end)]; text_value=" ".join(s.narration for s in block); toks=_tokens(text_value); first=_tokens(block[0].narration); last=_tokens(block[-1].narration)
                semantic=_feature(toks,SEMANTIC); topic=_tokens(story.topic+" "+story.title+" "+story.description)
                topic_score=min(1.0,len(toks&topic)/8.0) if topic else .5
                visual=min(1.0,.36*len(block)+.18*len({str(s.visual_intent).casefold().strip() for s in block})+.12*sum(bool(s.callouts) for s in block)+.18*len({str(s.layout) for s in block}))
                candidates.append(ShortCandidate(f"{start:02d}-{end:02d}-{int(start_offset*10):02d}-{int(end_trim*10):02d}",start,end,round(start_offset,3),round(end_trim,3),round(start_time,3),round(end_time,3),round(duration,3),_feature(first,HOOK),_feature(toks,PEAK),_feature(last,PAYOFF),semantic,visual,topic_score,_title(story,start,end)))
    candidates.sort(key=lambda x:(-x.score,x.candidate_id)); return candidates

def select_best(candidates,vectors=None):
    if len(candidates)<MIN_CANDIDATES: raise RuntimeError(f"SHORT CANDIDATE POOL FAILED: {len(candidates)} < {MIN_CANDIDATES}")
    vectors=vectors or {}; pool=candidates[:50]; best=None; best_key=None
    for combo in itertools.combinations(pool,4):
        sets=[set(x.scene_ids) for x in combo]
        if any(sets[i]&sets[j] for i in range(4) for j in range(i+1,4)): continue
        sigs=[_candidate_vector(x,vectors) for x in combo]
        min_dist=min((_distance(a,b) for a,b in itertools.combinations(sigs,2)),default=0.0) if vectors else 0.0
        key=(min_dist>=FINAL_MIN_DISTANCE,round(min_dist,6),round(sum(x.score for x in combo),6))
        if best_key is None or key>best_key: best_key,best=key,combo
    if best is None: raise RuntimeError("SHORT SELECTION FAILED: four disjoint candidates unavailable")
    return list(best)

def select_shorts(story,visual_dir,manifest_path=RUN/"short_candidates.json"):
    vectors={s.id:_scene_visual_vector(visual_dir/f"scene_{s.id:02d}.png") for s in story.scenes if (visual_dir/f"scene_{s.id:02d}.png").is_file()}
    candidates=build_candidates(story,visual_dir); selected=select_best(candidates,vectors)
    payload={"contract_version":"wangp-v1","selection_policy":"dynamic-two-scene-windows","pool_size":len(candidates),"required_pool_size":MIN_CANDIDATES,"selection_thresholds":{"short_min_seconds":SHORT_MIN_SECONDS,"short_max_seconds":SHORT_MAX_SECONDS,"min_predicted_pixel_distance":FINAL_MIN_DISTANCE},"candidates":[c.__dict__|{"scene_ids":list(c.scene_ids),"score":round(c.score,6)} for c in candidates],"selected":[c.__dict__|{"scene_ids":list(c.scene_ids),"score":round(c.score,6)} for c in selected]}
    manifest_path.parent.mkdir(parents=True,exist_ok=True); manifest_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return payload

def load_selected(manifest_path=RUN/"short_candidates.json"):
    selected=json.loads(manifest_path.read_text(encoding="utf-8")).get("selected")
    if not isinstance(selected,list) or len(selected)!=4: raise RuntimeError("SHORT SELECTION FAILED: manifest must contain four candidates")
    return selected
