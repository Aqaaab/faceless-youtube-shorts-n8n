import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault("RUN_DIR", "/tmp/aqaaab-router-test")
os.environ.setdefault("LONG_MIN_WORDS", "1050")
os.environ.setdefault("LONG_MAX_WORDS", "2100")
os.environ.setdefault("LONG_MIN_SCENES", "18")
os.environ.setdefault("LONG_MAX_SCENES", "30")

from scripts.ai_router import AIRouter, Provider
from scripts.patent_story_engine import validate


def make_scene(i):
    en=f"Scene {i} reveals a concrete detail about the investigation, showing why the evidence matters and how the clues changed the direction of the case."
    while len(en.split()) < 45:
        en += " Researchers compared records, photographs, maps, dates, and physical traces before drawing a cautious conclusion."
    en=" ".join(en.split()[:60])
    return {"text_en":en,"text_ar":"يكشف هذا المشهد تفصيلاً واضحاً في التحقيق، ويوضح أهمية الأدلة وكيف غيّرت القرائن مسار القضية.","visual_subject":"archival evidence","pexels_query":"archival evidence investigation","beat":("hook","setup","mystery","escalation","evidence","reveal","payoff","ending")[i%8]}


def test_validate_contract():
    scenes=[make_scene(i) for i in range(20)]
    doc={"topic":"Regression test story","category":"Stories","title":"Regression Test Story","description":"This is a test story sentence. It validates the long-form contract. It contains no production claims.","tags":["story","mystery","history","evidence","research","discovery","documentary","explained"],"scenes":scenes}
    out=validate(doc)
    assert out["scene_count"]==20
    assert 1050 <= out["script_words"] <= 2100
    bad=dict(doc); bad["scenes"]=scenes[:17]
    try: validate(bad)
    except ValueError as exc: assert "scene count" in str(exc)
    else: raise AssertionError("17 scenes must be rejected")


def test_router_fallback_after_rate_limit():
    calls=[]
    def fail(_):
        calls.append("first")
        raise RuntimeError("HTTP 429: Rate limit reached. Please try again in 1s")
    def succeed(_):
        calls.append("second"); return {"ok":True}
    router=AIRouter([Provider("first",["long_story"],1,True,fail,"m1"),Provider("second",["long_story"],2,True,succeed,"m2")])
    result,provider,model=router.route("Return JSON")
    assert result=={"ok":True} and provider=="second" and model=="m2" and calls==["first","second"]
    assert router._entry("first")["status"]=="RATE_LIMIT"

if __name__=="__main__":
    test_validate_contract(); test_router_fallback_after_rate_limit(); print("LONG_STORY_ROUTING_REGRESSION=PASS")
