import ast
from pathlib import Path

SOURCE = Path("scripts/patent_story_engine.py").read_text(encoding="utf-8")

def test_slot_engine_owns_router_cooldown_waiting():
    tree = ast.parse(SOURCE)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "route":
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords if kw.arg in {"wait_for_ready", "max_wait_seconds"}}
            calls.append(kwargs)
    assert calls, "patent_story_engine must call AIRouter.route"
    assert any(call.get("wait_for_ready") is False for call in calls), calls

def test_slot_engine_has_bounded_cooldown_wait():
    assert "LONG_MAX_COOLDOWN_WAIT" in SOURCE
    assert "LONG_STORY_WAIT_FOR_PROVIDER_COOLDOWN" in SOURCE
    assert "if delay>MAX_COOLDOWN_WAIT: return False" in SOURCE
