from __future__ import annotations
import hashlib, json
from pathlib import Path
from .core import RUN, Story
from .visual_product_gate import run_visual_product_gate
from .mp4_visual_gate import run_mp4_visual_product_gate

def _sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def qa(story:Story, final:Path, shorts:list[Path])->dict:
    errors=[]
    try: visual=run_visual_product_gate(story,final,shorts,RUN/"visual_product_gate.json",True)
    except Exception as exc:
        errors.append(str(exc)); visual=json.loads((RUN/"visual_product_gate.json").read_text(encoding="utf-8")) if (RUN/"visual_product_gate.json").is_file() else {"passed":False,"errors":[str(exc)]}
    try: mp4=run_mp4_visual_product_gate(final,shorts,RUN/"mp4_visual_product_gate.json")
    except Exception as exc:
        errors.append(str(exc)); mp4=json.loads((RUN/"mp4_visual_product_gate.json").read_text(encoding="utf-8")) if (RUN/"mp4_visual_product_gate.json").is_file() else {"passed":False,"errors":[str(exc)]}
    required=[RUN/"arabic_font_gate.json",RUN/"short_candidates.json",RUN/"thumbnail.jpg"]
    errors += [f"missing evidence: {p.name}" for p in required if not p.is_file()]
    passed=bool(visual.get("passed")) and bool(mp4.get("passed")) and not errors
    score=10.0 if passed else min(float(visual.get("average_score",0))/10.0,9.9)
    report={"passed":passed,"errors":errors,"weighted_score_10":round(score,3),"master_sha256":_sha(final) if final.is_file() else None,"short_shas":[_sha(p) for p in shorts if p.is_file()],"visual_product_gate":visual,"mp4_visual_product_gate":mp4,"cost_usd":0.0,"paid_services_used":[],"renderer":"wangp","renderer_contract":"wangp-v1"}
    (RUN/"qa_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if not passed: raise RuntimeError("FINAL QA FAILED: "+"; ".join(errors or visual.get("errors",[]) or mp4.get("errors",[])))
    return report
