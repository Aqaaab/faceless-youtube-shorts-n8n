from .artifact_gate import qa as _legacy_qa
from .visual_product_gate import run_visual_product_gate


def qa(story, master, shorts, report=None):
    result = _legacy_qa(story, master, shorts, report) if report is not None else _legacy_qa(story, master, shorts)
    visual = run_visual_product_gate(story, master, shorts)
    result["visual_product_gate_v3"] = visual
    if report is not None:
        report.write_text(__import__("json").dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = ["qa"]
