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


def test_no_production_dependency_on_legacy_visual_module():
    for p in [ROOT/'app'/'pipeline.py',ROOT/'app'/'render.py',ROOT/'app'/'qa.py']:
        text=p.read_text(encoding='utf-8')
        assert 'from .visuals import' not in text
    assert 'from .story_visuals import _kind' in (ROOT/'app'/'qa.py').read_text(encoding='utf-8')


def test_production_is_manual_and_publish_is_after_final_gate():
    t=(ROOT/'.github'/'workflows'/'production.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in t
    assert 'push:' not in t and 'schedule:' not in t
    assert 'test -s work/master_final.mp4' in t
    assert "assert r['passed'] is True" in t
    assert 'if: ${{ inputs.publish }}' in t
    assert t.index('Final artifact gate') < t.index('YouTube upload')


def test_required_qa_gates_are_present():
    t=(ROOT/'app'/'qa.py').read_text(encoding='utf-8')
    for token in ['len(story.scenes) != 25','1080,1920','SHORT_MIN','_black_bars','subtitle_burn.json','short_subtitles_burn.json','title','description','tags','MAX_WORDS','visual intent not rendered','callout not rendered']:
        assert token in t, f'missing hardened QA gate: {token}'


def test_pipeline_has_tts_timing_gate():
    t=(ROOT/'app'/'pipeline.py').read_text(encoding='utf-8')
    assert 'generate_tts' in t
    assert 'synchronize_scene_durations' in t
    assert 'validate_tts_timing' in t
    assert 'tts_durations.json' in t
    assert 'story_visuals' in t
    assert t.index('generate_tts(story)') < t.index('validate_tts_timing(story, tts_durations)')
    assert t.index('synchronize_scene_durations') < t.index('render_long(story)')


def test_story_engine_has_tts_pacing_contract():
    t=(ROOT/'app'/'core.py').read_text(encoding='utf-8')
    for token in ['1.8-2.2 Arabic words per second','14-24 seconds','28-50 narration words','measured Arabic TTS','Callouts must be directly supported by the scene narration','Do not invent quantitative claims']:
        assert token in t, f'missing story pacing/grounding rule: {token}'
    assert 'short_titles' in t


def test_tts_module_has_bounded_adaptive_rates_and_short_ceiling():
    t=(ROOT/'app'/'tts.py').read_text(encoding='utf-8')
    for token in ['MAX_SLOWDOWN = -20','MAX_SPEEDUP = 20','SHORT_TARGET = 58.0','synchronize_scene_durations','DURATION_PADDING = 0.5']:
        assert token in t


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


def test_story_visual_engine_renders_callouts_and_intent(tmp_path):
    from app.core import Scene
    from app.story_visuals import render_scene_svg
    scene=Scene(1,'هذه جملة عربية كافية للمشهد وتشرح الأداء بطريقة واضحة ومباشرة للمشاهد مع تفاصيل مفيدة هنا','لقطة تقنية تشرح نظام الدفع والاستجابة مع مخطط واضح للعلاقة بين المكونات','technical',['320 حصان','عزم 450 نيوتن متر'],17)
    out=tmp_path/'scene.svg'
    render_scene_svg(scene,'سيارة اختبار',out)
    text=out.read_text(encoding='utf-8')
    assert '320 حصان' in text
    assert 'عزم 450 نيوتن متر' in text
    assert 'data-visual-mode="performance"' in text
    assert 'data-layout="technical"' in text


def test_story_visual_engine_renders_long_intent(tmp_path):
    from app.core import Scene
    from app.story_visuals import render_scene_svg
    intent='مخطط بصري طويل يوضح تسلسل النظام وموقع العناصر الرئيسية داخل السيارة بشكل واضح'
    scene=Scene(2,'هذه جملة عربية كافية للمشهد وتشرح التقنية بطريقة واضحة ومباشرة للمشاهد مع تفاصيل مفيدة هنا',intent,'diagram',['نظام الدفع'],17)
    out=tmp_path/'scene.svg'
    render_scene_svg(scene,'سيارة اختبار',out)
    text=out.read_text(encoding='utf-8')
    assert intent in text
    assert 'نظام الدفع' in text
    assert 'data-layout="diagram"' in text


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
    return {'title':'اختبار السيارة الجديدة بالتفصيل','description':'هذا وصف إنتاجي مفصل يشرح السيارة وأبرز المواصفات والأداء والتقنيات والتجربة بشكل واضح للمشاهد مع معلومات مفيدة ومنظمة، ويقدم سياقا كافيا للمحتوى ويضمن وجود بيانات وصفية قوية وقابلة للاستخدام في النشر على يوتيوب.','tags':['cars','automotive','review','specs','performance'],'short_titles':['لماذا هذه السيارة مختلفة في الأداء؟','تفصيل مهم في تصميم السيارة الجديدة','التقنية التي تغيّر تجربة القيادة','هل تستحق السيارة سعرها فعلًا؟'],'narration':' '.join(s['narration'] for s in scenes),'scenes':scenes}


def test_validator_accepts_strong_story(tmp_path):
    p=tmp_path/'story.json'; p.write_text(json.dumps(_strong_story(),ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    assert validate_story(p) is True


def test_validator_rejects_scene_over_75_words(tmp_path):
    data=_strong_story(); data['scenes'][0]['narration']=' '.join(['كلمة']*76); data['narration']=' '.join(s['narration'] for s in data['scenes'])
    p=tmp_path/'story.json'; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    with pytest.raises(AssertionError,match='25-75 words'): validate_story(p)


def test_validator_rejects_unsupported_numeric_callout(tmp_path):
    data=_strong_story(); data['scenes'][0]['callouts']=['320 حصان']
    p=tmp_path/'story.json'; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    with pytest.raises(AssertionError,match='unsupported numeric claim'): validate_story(p)


def test_validator_accepts_grounded_numeric_callout(tmp_path):
    data=_strong_story(); data['scenes'][0]['narration']=data['scenes'][0]['narration']+' بقوة 320 حصان'; data['narration']=' '.join(s['narration'] for s in data['scenes']); data['scenes'][0]['callouts']=['320 حصان']
    p=tmp_path/'story.json'; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    assert validate_story(p) is True


def test_validator_accepts_arabic_indic_numeric_form(tmp_path):
    data=_strong_story(); data['scenes'][0]['narration']=data['scenes'][0]['narration']+' بقوة ٣٢٠ حصان'; data['narration']=' '.join(s['narration'] for s in data['scenes']); data['scenes'][0]['callouts']=['320 حصان']
    p=tmp_path/'story.json'; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    from app.validator import validate_story
    assert validate_story(p) is True


def test_synchronize_scene_durations_never_truncates_audio():
    from app.core import Scene
    from app.tts import synchronize_scene_durations
    story=type('S',(),{})(); story.scenes=[Scene(1,'نص عربي كاف لهذا الاختبار مع كلام واضح ومفهوم ومناسب للمشهد','visual intent with enough detail here','hero',[],18)]
    synchronize_scene_durations(story,{1:27.74})
    assert story.scenes[0].duration >= 28.24


def test_tts_timing_gate_rejects_audio_overrun():
    from app.tts import validate_tts_timing
    story=type('S',(),{})(); story.scenes=[type('C',(),{'id':1,'duration':10})()]
    with pytest.raises(RuntimeError,match='TTS TIMING FAILED'): validate_tts_timing(story,{1:11.5})


def test_tts_timing_gate_accepts_reasonable_padding():
    from app.tts import validate_tts_timing
    story=type('S',(),{})(); story.scenes=[type('C',(),{'id':1,'duration':17})()]
    validate_tts_timing(story,{1:15.8})


def test_youtube_title_always_stays_within_100_chars():
    from app.upload import _final_title
    marker=' [ACE:123456789abc]'; result=_final_title('x'*100,marker)
    assert len(result)<=100 and result.endswith(marker)


def test_youtube_metadata_removes_control_characters():
    from app.upload import _clean_text
    result=_clean_text('عنوان\x00\x07\nوصف',5000)
    assert '\x00' not in result and '\x07' not in result and 'عنوان' in result and 'وصف' in result


def test_youtube_duplicate_search_omits_invalid_for_mine_and_empty_page_token():
    from app.upload import existing_titles
    class FakeRequest:
        def __init__(self,response): self.response=response
        def execute(self): return self.response
    class FakeChannels:
        def list(self,**kwargs): assert kwargs=={'part':'id','mine':True}; return FakeRequest({'items':[{'id':'channel-1'}]})
    class FakeSearch:
        def __init__(self): self.calls=[]
        def list(self,**kwargs):
            self.calls.append(kwargs); assert 'forMine' not in kwargs; assert kwargs['channelId']=='channel-1'; assert 'pageToken' not in kwargs
            return FakeRequest({'items':[{'snippet':{'title':'video [ACE:test123]'}}]})
    class FakeService:
        def __init__(self): self.search_api=FakeSearch()
        def channels(self): return FakeChannels()
        def search(self): return self.search_api
    svc=FakeService(); assert existing_titles(svc,'[ACE:test123]') is True; assert len(svc.search_api.calls)==1


def test_render_delivery_contracts_are_hardened():
    t=(ROOT/'app'/'render.py').read_text(encoding='utf-8')
    assert 'FontName=Noto Sans Arabic' in t and 'FontSize=24' in t and 'MarginV=76' in t and 'WrapStyle=2' in t
    assert 'loudnorm=I=-16:TP=-1.5:LRA=11' in t and "zoompan=z='min(1.0+on/" in t
    assert '1920x1080' in t and '1080x1920' in t


def test_upload_is_blocked_without_final_visual_qa(tmp_path):
    from app.upload import _require_final_qa
    (tmp_path/'master_final.mp4').write_bytes(b'video')
    for i in range(1,5):
        p=tmp_path/'shorts'/f'short_{i}.mp4'; p.parent.mkdir(exist_ok=True); p.write_bytes(b'video')
    (tmp_path/'qa_report.json').write_text(json.dumps({'passed':False}),encoding='utf-8')
    with pytest.raises(RuntimeError,match='UPLOAD BLOCKED'): _require_final_qa(tmp_path)


def test_upload_requires_visual_product_gate_evidence(tmp_path):
    (tmp_path/'master_final.mp4').write_bytes(b'video')
    for i in range(1,5):
        p=tmp_path/'shorts'/f'short_{i}.mp4'; p.parent.mkdir(exist_ok=True); p.write_bytes(b'video')
    (tmp_path/'qa_report.json').write_text(json.dumps({'passed':True,'visual_product_gate':{'average_score':84}}),encoding='utf-8')
    from app.upload import _require_final_qa
    with pytest.raises(RuntimeError,match='visual product gate'): _require_final_qa(tmp_path)
