from pathlib import Path
import json
import sys
import pytest

ROOT=Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    with pytest.raises(AssertionError, match='25-75 words'):
        validate_story(p)
