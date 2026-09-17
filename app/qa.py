import json
from pathlib import Path

from .artifact_gate import qa as technical_qa
from .core import RUN
from .visual_product_gate import run_visual_product_gate


def qa(story, master: Path, shorts: list[Path], report: Path = None):
    """Run technical QA, then mandatory rendered-product QA, and persist both."""
    report_path = Path(report) if report else RUN / "qa_report.json"
    result = technical_qa(story, master, shorts, report=report_path)
    visual_report = Path(master).parent / "visual_product_gate_v4.json"
    visual = run_visual_product_gate(story, master, shorts, report=visual_report)
    result["visual_product_gate"] = visual
    result["product_pass"] = bool(visual.get("passed"))
    result["weighted_score_10"] = min(float(result.get("weighted_score_10", 10.0)), 10.0)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = ["qa"]
