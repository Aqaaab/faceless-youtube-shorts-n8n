from __future__ import annotations
import hashlib, json, os, shutil
from pathlib import Path
from app.core import Scene, Story
from app.wangp import WanGPClient, generate_visuals
from app.mp4_visual_gate import _check

ROOT=Path("."); WORK=ROOT/"work"; OUT=WORK/"ci-wangp-smoke"

def fixture_story():
    scene=Scene(
        1,
        "هذه لقطة اختبارية لسيارة واقعية مع تفاصيل واضحة وتصميم متوازن وتقنية حديثة وحركة سينمائية هادئة للاختبار",
        "لقطة سيارة واقعية ثلاثية الأرباع مع حركة كاميرا سينمائية وتفاصيل هيكلية واضحة",
        "hero",
        ["تصميم متوازن"],
        5.0,
    )
    return Story(
        "سيارة اختبار WanGP",
        "اختبار بصري WanGP للسيارة",
        "اختبار تكامل فعلي لمسار WanGP مع مرجع واحد ومشهد متحرك.",
        ["سيارات","WanGP","اختبار","فيديو","ذكاء اصطناعي"],
        ["اختبار بصري للسيارة في WanGP","حركة سيارة واقعية في لقطة قصيرة","كيف نحافظ على هوية السيارة؟","لقطة مرجعية مترابطة"],
        scene.narration,
        [scene],
    )

def main():
    if not os.getenv("WANGP_MCP_URL","").strip():
        raise SystemExit("WANGP_MCP_URL is required for the real WanGP smoke")
    shutil.rmtree(OUT,ignore_errors=True); OUT.mkdir(parents=True,exist_ok=True)
    health=WanGPClient().check()
    story=fixture_story()
    scene_dir=OUT/"scenes"; generate_visuals(story,scene_dir)
    mp4=scene_dir/"scene_01.mp4"; png=scene_dir/"scene_01.png"; meta=scene_dir/"scene_01.json"
    gate=_check(mp4,(1920,1080),4.0,7.0)
    if not gate["passed"]: raise SystemExit(json.dumps(gate,ensure_ascii=False))
    payload={
        "passed":True,"renderer":"wangp","contract":"wangp-v1","health":health,
        "scene":{"video":str(mp4),"preview":str(png),"metadata":str(meta),"sha256":hashlib.sha256(mp4.read_bytes()).hexdigest(),"gate":gate},
        "cost_usd":0.0,"paid_services_used":[],
    }
    (WORK/"ci_wangp_smoke.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False))

if __name__=="__main__":
    main()
