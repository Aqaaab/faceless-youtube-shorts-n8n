import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("RUN_DIR", "/tmp/aqaaab-router-test")
os.environ.setdefault("LONG_MIN_WORDS", "1050")
os.environ.setdefault("LONG_MAX_WORDS", "2100")
os.environ.setdefault("LONG_MIN_SCENES", "18")
os.environ.setdefault("LONG_MAX_SCENES", "30")

from scripts.ai_router import AIRouter, Provider
from scripts.patent_story_engine import validate_final


def make_scene(i):
    en=(f"Scene {i} reveals a concrete detail about the investigation, showing why the evidence matters and how the clues changed the direction of the case.")
    while len(en.split()) < 45:
        en += " Researchers compared records, photographs, maps, dates, and physical traces before drawing a cautious conclusion."
    en=" ".join(en.split()[:60])
    return {"text_en": en, "text_ar": "يكشف هذا المشهد تفصيلاً واضحاً في التحقيق، ويوضح أهمية الأدلة وكيف غيّرت القرائن مسار القضية.", "visual_subject": "archival evidence", "pexels_query": "archival evidence investigation", "beat": ("hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending")[i % 8]}


class TestLongStoryRouting(unittest.TestCase):
    def test_validate_contract(self):
        scenes=[make_scene(i) for i in range(24)]
        doc={"topic":"Regression test story","category":"Stories","title":"Regression Test Story","description":"This is a test story sentence. It validates the long-form contract. It contains no production claims.","tags":["story","mystery","history","evidence","research","discovery","documentary","explained"],"scenes":scenes}
        out=validate_final(doc)
        self.assertEqual(out["scene_count"],24)
        self.assertTrue(1050 <= out["script_words"] <= 2100)
        bad=dict(doc); bad["scenes"]=scenes[:17]
        with self.assertRaisesRegex(ValueError, "scene count"):
            validate_final(bad)

    def test_router_fallback_after_rate_limit(self):
        calls=[]
        def fail(_): calls.append("first"); raise RuntimeError("HTTP 429: Rate limit reached. Please try again in 1s")
        def succeed(_): calls.append("second"); return {"ok": True}
        router=AIRouter([Provider("first",["long_story"],1,True,fail,"m1"),Provider("second",["long_story"],2,True,succeed,"m2")])
        result,provider,model=router.route("Return JSON")
        self.assertEqual(result,{"ok":True})
        self.assertEqual(provider,"second")
        self.assertEqual(model,"m2")
        self.assertEqual(calls,["first","second"])
        self.assertEqual(router._entry("first")["status"],"RATE_LIMIT")

    def test_router_waits_then_recovers_from_cooldown(self):
        calls=[]
        def first(_): calls.append("first"); raise RuntimeError("HTTP 429: rate limit")
        def second(_): calls.append("second"); return {"ok": 2}
        router=AIRouter([Provider("first",["long_story"],1,True,first,"m1"),Provider("second",["long_story"],2,True,second,"m2")])
        router._entry("first")["cooldown_until"]=time.time()+1
        router._entry("second")["cooldown_until"]=time.time()+1
        result,provider,model=router.route("Return JSON",wait_for_ready=True,max_wait_seconds=5)
        self.assertEqual(result,{"ok":2})
        self.assertEqual(provider,"second")
        self.assertEqual(model,"m2")
