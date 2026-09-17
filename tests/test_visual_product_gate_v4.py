from pathlib import Path


def test_v4_visual_contracts():
    root = Path(__file__).parents[1]
    render = (root / "app" / "render.py").read_text(encoding="utf-8")
    visual = (root / "app" / "visual_product_gate.py").read_text(encoding="utf-8")
    artifact = (root / "app" / "artifact_gate.py").read_text(encoding="utf-8")
    production = (root / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
    assert "BorderStyle=1" in render
    assert "_caption_chunks" in render and "_wrap_caption" in render
    assert 'data-car-layer="primary"' in visual
    assert '"gate_version"' in visual and '"v4"' in visual
    assert "subtitle visual occupancy/edge safety failed" in visual
    assert "run_visual_product_gate" in artifact
    assert "visual_product_gate" in production
    assert "unique_visual_families" in production and "unique_motions" in production
