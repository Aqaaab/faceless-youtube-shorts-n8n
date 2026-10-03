from __future__ import annotations
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]

def _source_text():
    chunks=[]
    for root in (ROOT/"app",ROOT/"scripts",ROOT/"tests",ROOT/".github"/"workflows",ROOT/"config"):
        if not root.exists(): continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py",".yml",".yaml",".json"} and path != Path(__file__):
                chunks.append(path.read_text(encoding="utf-8",errors="ignore"))
    return "\n".join(chunks)

def strong_story(duration=18.0):
    base="السيارة الجديدة تجمع بين تصميم عملي وتقنيات حديثة وأداء متوازن يمنح السائق تجربة واضحة ومتماسكة في الاستخدام اليومي، مع تركيز على التفاصيل الهندسية التي تميز هذا الطراز ضمن فئته دون مبالغة أو ادعاءات غير مثبتة"
    layouts=["hero","technical","spec","comparison","diagram","timeline"]; scenes=[]
    for sid in range(1,26):
        narration=base+f" في المشهد رقم {sid}."
        callouts=["تصميم عملي","تقنيات حديثة"] if sid%2 else ["أداء متوازن","تجربة واضحة"]
        if sid==1: narration+=" قوة 320 حصان."; callouts=["320 حصان","أداء متوازن"]
        scenes.append({"id":sid,"narration":narration,"visual_intent":f"لقطة سيارة واقعية للمشهد {sid} مع حركة وتفصيل هندسي واضح للمعلومة الأساسية","layout":layouts[(sid-1)%6],"callouts":callouts,"duration":duration})
    return {"topic":"سيارة جديدة","title":"السيارة الجديدة بالتفصيل: التصميم والتقنية والأداء","description":"تحليل عربي منظم للسيارة الجديدة يشرح التصميم والتقنيات والأداء وتجربة الاستخدام عبر خمسة وعشرين مشهداً مترابطاً مع معلومات واضحة وعناوين مستقلة للمقاطع القصيرة.","tags":["سيارات","مراجعة","تقنية","أداء","تصميم"],"short_titles":["لماذا يلفت تصميم هذه السيارة الانتباه؟","ما الذي يميز أداء السيارة في الاستخدام اليومي؟","التقنية التي تجعل تجربة القيادة أكثر وضوحاً","هل تجمع السيارة بين الأداء والتصميم بشكل متوازن؟"],"narration":" ".join(s["narration"] for s in scenes),"scenes":scenes}

def test_no_old_renderer_or_stock_paths():
    source=_source_text().lower()
    forbidden=[bytes.fromhex(x).decode() for x in ("626c656e646572","7261737465725f6175746f6d6f74697665","2e6d6f74696e672e6d7034","7363656e652d72656e646572","73686f72745f67726f757073","72656e6465725f7363656e655f626c656e646572","76697375616c5f70726f647563745f676174655f7633","706578656c73")]
    assert not [x for x in forbidden if x in source], [x for x in forbidden if x in source]

def test_canonical_contract():
    from app.production_contract import SCENE_COUNT,SCENE_IDS,LANDSCAPE_DELIVERY,PORTRAIT_DELIVERY,SHORT_MIN_SECONDS,SHORT_MAX_SECONDS,SHORT_DELIVERY_COUNT,SHORT_CANDIDATE_MINIMUM
    assert SCENE_COUNT==25 and SCENE_IDS==tuple(range(1,26))
    assert LANDSCAPE_DELIVERY==(1920,1080) and PORTRAIT_DELIVERY==(1080,1920)
    assert (SHORT_MIN_SECONDS,SHORT_MAX_SECONDS)==(28.0,59.0)
    assert SHORT_DELIVERY_COUNT==4 and SHORT_CANDIDATE_MINIMUM==30

def test_story_validator_uses_canonical_duration_and_ids(tmp_path):
    from app.validator import validate_story
    path=tmp_path/"story.json"; path.write_text(json.dumps(strong_story(),ensure_ascii=False),encoding="utf-8")
    assert validate_story(path)

def test_tts_timing_updates_story_duration():
    from app.core import Scene
    from app.tts import DURATION_PADDING,synchronize_scene_durations
    story=type("S",(),{})(); story.scenes=[Scene(1,"نص عربي مناسب للاختبار مع معلومات واضحة ومتماسكة","لقطة سيارة واقعية مع حركة وتفصيل واضح","hero",[],18)]
    synchronize_scene_durations(story,{1:10.0})
    assert story.scenes[0].duration==pytest.approx(10.0+DURATION_PADDING)

def test_wangp_source_contract():
    src=(ROOT/"app"/"wangp.py").read_text(encoding="utf-8")
    for token in ("wangp_models","wangp_model","wangp_generate","wangp_get_job","wangp_create_gallery_download","image_refs","image_start","video_prompt_type","video_length","force_fps"):
        assert token in src

def test_render_source_is_wangp_agnostic_and_ffmpeg_delivery():
    src=(ROOT/"app"/"render.py").read_text(encoding="utf-8")
    for token in ("1920, 1080","1080, 1920","libx264","loudnorm=I=-16:TP=-1.5:LRA=11"):
        assert token in src

def test_final_qa_upload_contract():
    upload=(ROOT/"app"/"upload.py").read_text(encoding="utf-8")
    workflow=(ROOT/".github"/"workflows"/"production.yml").read_text(encoding="utf-8")
    for token in ("visual_product_gate.json","mp4_visual_product_gate.json","renderer_contract","weighted_score_10"):
        assert token in upload
    assert "visual_product_gate.json" in workflow
    assert "mp4_visual_product_gate.json" in workflow
    assert "YouTube upload" in workflow
    assert workflow.index("Final artifact product gate") < workflow.index("YouTube upload")


def test_cache_key_contains_contract_scene_duration_aspect_model_and_reference():
    from app.cache import scene_key
    a=scene_key(topic="A",profile="p",scene_id=1,duration=18,aspect_ratio="16:9",model_type="m",prompt="x",reference_id="r1",seed=7)
    b=scene_key(topic="A",profile="p",scene_id=1,duration=19,aspect_ratio="16:9",model_type="m",prompt="x",reference_id="r1",seed=7)
    c=scene_key(topic="A",profile="p",scene_id=1,duration=18,aspect_ratio="9:16",model_type="m",prompt="x",reference_id="r1",seed=7)
    d=scene_key(topic="A",profile="p",scene_id=1,duration=18,aspect_ratio="16:9",model_type="m",prompt="x",reference_id="r2",seed=7)
    assert len({a,b,c,d}) == 4

def test_checkpoint_revision_invalidates_previous_renderer_state(tmp_path):
    from app.checkpoint import begin, mark, load
    work=tmp_path/"work"
    first=begin(work,"topic","premium_coupe")
    mark(first,work,"visuals","done",[])
    second=begin(work,"topic","premium_coupe")
    assert second["pipeline_revision"] == "2026-10-wangp-v1"
    assert second.get("stages",{}) == {}

def test_short_selection_contract_forbids_fixed_pairs():
    assert "fixed" not in (Path(ROOT/"app"/"short_selector.py").read_text(encoding="utf-8").lower().split("def select_best",1)[0])
