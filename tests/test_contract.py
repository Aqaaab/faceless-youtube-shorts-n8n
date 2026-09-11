from pathlib import Path
import json
import sys
import pytest

ROOT=Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def test_source_is_clean():
    tokens=['pex'+'els','render_'+'manifest.json','generated_'+'still_first','stock-'+'video']
    for p in ROOT.rglob('*'):
        if not p.is_file() or '.git' in p.parts: continue
        if p.suffix in {'.py','.yml','.yaml','.md','.json','.txt'}:
            text=p.read_text(encoding='utf-8',errors='ignore').lower()
            for token in tokens: assert token not in text, f'forbidden legacy token in {p}'


def test_required_qa_gates_are_present():
    t=(ROOT/'app'/'qa.py').read_text(encoding='utf-8')
    for token in ['len(story.scenes) != 25','1080,1920','SHORT_MIN','_black_bars','subtitle_burn.json','short_subtitles_burn.json','title','description','tags','MAX_WORDS']:
        assert token in t, f'missing hardened QA gate: {token}'


def test_pipeline_has_tts_timing_gate():
    t=(ROOT/'app'/'pipeline.py').read_text(encoding='utf-8')
    assert 'validate_tts_timing' in t
    assert 'tts_durations.json' in t
    assert 'story_visuals' in t


def test_story_engine_has_tts_pacing_contract():
    t=(ROOT/'app'/'core.py').read_text(encoding='utf-8')
    for token in ['1.8-3.0 Arabic words per second','14-24 seconds','28-60 narration words','Callouts must be directly supported by the scene narration','Do not invent quantitative claims']:
        assert token in t, f'missing story pacing/grounding rule: {token}'


def test_vertical_engine_has_semantic_scene_modes():
    t=(ROOT/'app'/'vertical_visuals.py').read_text(encoding='utf-8')
    for token in ['performance','design','interior','technology','efficiency','safety','price']:
        assert f'"{token}"' in t


def test_story_visual_engine_has_no_fabricated_metrics():
    t=(ROOT/'app'/'story_visuals.py').read_text(encoding='utf-8')
    forbidden=['82 / 100','74 / 100','91 / 100','LONG DISTANCE','LOW LOSS','360° PROTECTION','OPTIMIZED ZONE']
    for token in forbidden:
        assert token not in t, f'fabricated visual metric/value remains: {token}'
    assert 'STORY CALLOUT' in t
    assert 'scene.callouts' in t


def test_story_visual_engine_renders_callouts(tmp_path):
    from app.core import Scene
    from app.story_visuals import render_scene_svg
    scene=Scene(1,'هذه جملة عربية كافية للمشهد وتشرح الأداء بطريقة واضحة ومباشرة للمشاهد مع تفاصيل مفيدة هنا','لقطة تقنية تشرح نظام الدفع والاستجابة','technical',['320 حصان','عزم 450 نيوتن متر'],17)
    out=tmp_path/'scene.svg'
    render_scene_svg(scene,'سيارة اختبار',out)
    text=out.read_text(encoding='utf-8')
    assert '320 حصان' in text
    assert 'عزم 450 نيوتن متر' in text
    assert 'data-visual-mode="performance"' in text
    assert 'data-layout="technical"' in text


def test_validator_rejects_weak_story(tmp_path):
    data={'title':'Untitled Story','description':'x','tags':[],'scenes':[{'id':1,'narration':'too short','visual_intent':'x','layout':'hero','duration':1}]}
    p=tmp_path/'story.json'; p.write_text(json.dumps(data),encoding='utf-8')
    from app.validator import validate_story
    with pytest.raises(AssertionError): validate_story(p)


def _strong_story():
    narration=' '.join(['سيارة','رياضية','جديدة','تقدم','أداء','قوي','مع','تصميم','متطور','وتقنيات','حديثة','تستحق','الاهتمام','في','هذه','الفئة','بشكل','واضح','ومفصل','للمشاهد','اليوم','أيضا','عمليا','وفعليا','هنا'])
    layouts=['hero','technical','spec','comparison','diagram','timeline']
    scenes=[]
    for i in range(1,26):
        scenes.append({'id':i,'narration':narration,'visual_intent':f'visual concept for scene {i} with automotive technical storytelling','layout':layouts[(i-1)%len(layouts)],'callouts':['power','range'],'duration':17})
    return {'title':'اختبار السيارة الجديدة بالتفصيل','description':'هذا وصف إنتاجي مفصل يشرح السيارة وأبرز المواصفات والأداء والتقنيات والتجربة بشكل واضح للمشاهد مع معلومات مفيدة ومنظمة، ويقدم سياقا كافيا للمحتوى ويضمن وجود بيانات وصفية قوية وقابلة للاستخدام في النشر على يوتيوب.','tags':['cars','automotive','review','specs','performance'],'narration':' '.join(s['narration'] for s in scenes),'scenes':scenes}


def test_validator_accepts_strong_story(tmp_path):
    p=tmp_path/'story.json'; p.write_text(json.dumps(_strong_story(),ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    assert validate_story(p) is True


def test_validator_rejects_scene_over_75_words(tmp_path):
    data=_strong_story()
    data['scenes'][0]['narration']=' '.join(['كلمة']*76)
    data['narration']=' '.join(s['narration'] for s in data['scenes'])
    p=tmp_path/'story.json'; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    with pytest.raises(AssertionError,match='25-75 words'):
        validate_story(p)


def test_youtube_title_always_stays_within_100_chars():
    from app.upload import _final_title
    marker=' [ACE:123456789abc]'
    result=_final_title('x'*100,marker)
    assert len(result)<=100
    assert result.endswith(marker)


def test_youtube_metadata_removes_control_characters():
    from app.upload import _clean_text
    result=_clean_text('عنوان\x00\x07\nوصف',5000)
    assert '\x00' not in result
    assert '\x07' not in result
    assert 'عنوان' in result and 'وصف' in result


def test_tts_timing_gate_rejects_audio_overrun():
    from app.tts import validate_tts_timing
    story=type('S',(),{})()
    story.scenes=[type('C',(),{'id':1,'duration':10})()]
    with pytest.raises(RuntimeError,match='TTS TIMING FAILED'):
        validate_tts_timing(story,{1:11.5})


def test_tts_timing_gate_accepts_reasonable_padding():
    from app.tts import validate_tts_timing
    story=type('S',(),{})()
    story.scenes=[type('C',(),{'id':1,'duration':17})()]
    validate_tts_timing(story,{1:15.8})
