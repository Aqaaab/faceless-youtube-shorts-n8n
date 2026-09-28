from pathlib import Path


def test_pipeline_runs_visual_and_mp4_gates_before_publish_artifact_is_ready():
    source=Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "run_visual_product_gate" in source
    assert "visual_product_gate_v3.json" in source
    assert "run_mp4_visual_product_gate" in source
    assert "and bool(visual_gate.get('passed'))" in source
    assert "and bool(mp4_gate.get('passed'))" in source


def test_upload_requires_both_final_visual_gates():
    source=Path("app/upload.py").read_text(encoding="utf-8")
    assert 'report.get("visual_product_gate_v3", {})' in source
    assert 'report.get("mp4_visual_product_gate", {})' in source
    assert "visual product gate did not pass" in source
    assert "MP4 visual product gate did not pass" in source


def test_production_workflow_requires_visual_gate_before_upload():
    source=Path(".github/workflows/production.yml").read_text(encoding="utf-8")
    assert "test -s work/visual_product_gate_v3.json" in source
    assert "v3.get('passed') is True" in source
    assert source.index("Final artifact product gate") < source.index("YouTube upload")


def test_production_render_consumes_raster_sources_directly():
    source=Path("app/render.py").read_text(encoding="utf-8")
    assert 'RUN / "scenes" / f"scene_{s.id:02d}.png"' in source
    assert 'RUN / "vertical_scenes" / f"scene_{s.id:02d}.png"' in source
    assert "from .production_contract import SHORT_GROUPS" in source
    assert 'list(SHORT_GROUPS)' in source
    assert '.svg", frame' not in source


def test_validator_short_groups_match_production_renderer():
    validator=Path("app/validator.py").read_text(encoding="utf-8")
    render=Path("app/render.py").read_text(encoding="utf-8")
    assert "from .production_contract import SHORT_GROUPS" in validator
    assert "from .production_contract import SHORT_GROUPS" in render
