from pathlib import Path


def test_pipeline_runs_v3_and_mp4_visual_gates_before_publish_artifact_is_ready():
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
    assert "v3 visual product gate did not pass" in source
    assert "MP4 visual product gate did not pass" in source


def test_production_workflow_requires_v3_gate_before_upload():
    source=Path(".github/workflows/production.yml").read_text(encoding="utf-8")
    assert "test -s work/visual_product_gate_v3.json" in source
    assert "v3.get('passed') is True" in source
    assert source.index("Final artifact product gate") < source.index("YouTube upload")


def test_production_render_consumes_raster_sources_directly():
    source=Path("app/render.py").read_text(encoding="utf-8")
    assert 'RUN / "scenes" / f"scene_{s.id:02d}.png"' in source
    assert 'RUN / "vertical_scenes" / f"scene_{s.id:02d}.png"' in source
    assert 'groups = [(1, 2), (3, 4), (5, 6), (7, 8)]' in source
    assert '.svg", frame' not in source


def test_validator_short_groups_match_production_renderer():
    source=Path("app/validator.py").read_text(encoding="utf-8")
    assert 'SHORT_GROUPS = ((1, 2), (3, 4), (5, 6), (7, 8))' in source
