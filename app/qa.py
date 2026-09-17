from pathlib import Path

from .artifact_gate import qa as technical_qa
from .visual_product_gate import run_visual_product_gate


def qa(story, master: Path, shorts: list[Path], report: Path = None):
    """Technical QA followed by mandatory product-quality QA.

    A technically valid artifact is not publishable until the rendered visual
    product gate also passes. This intentionally keeps CI/contract validation
    separate from actual product acceptance.
    """
    result = technical_qa(story, master, shorts, report=report or Path(__file__).resolve().parent.parent / "run" / "qa_report.json")
    visual_report = Path(master).parent / "visual_product_gate_v4.json"
    visual = run_visual_product_gate(story, master, shorts, report=visual_report)
    result["visual_product_gate"] = visual
    result["product_pass"] = bool(visual.get("passed"))
    return result


__all__ = ["qa"]
