import re
from pathlib import Path


def test_visual_product_gate_detects_svg_vector_primitives():
    source = Path("app/visual_product_gate.py").read_text(encoding="utf-8")
    assert r"<(?:path|rect|circle|ellipse|polygon|line)\b" in source
    assert not re.search(r"<(?:path|rect|circle|ellipse|polygon|line)\\\\b", source)


def test_visual_product_gate_requires_embedded_raster_evidence():
    source = Path("app/visual_product_gate.py").read_text(encoding="utf-8")
    assert 'data-asset-quality="blender_eevee_automotive_v1"' in source
    assert 'data:image/png;base64,' in source
