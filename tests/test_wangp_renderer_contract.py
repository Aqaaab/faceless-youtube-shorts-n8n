from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).parents[1]

def test_wangp_is_single_visual_engine():
    src=(ROOT/"app"/"wangp.py").read_text(encoding="utf-8")
    for token in ("class WanGPClient","wangp_models","wangp_model","wangp_generate","wangp_get_job","wangp_create_gallery_download"):
        assert token in src
    assert "ensure_persistent_asset" not in src
    assert "render_"+"scene_"+"blender" not in src

def test_wangp_preserves_reference_inputs():
    src=(ROOT/"app"/"wangp.py").read_text(encoding="utf-8")
    for token in ('"image_refs"','"reference_media_id"','"video_prompt_type"','"subject_priority"'):
        assert token in src
    assert '"renderer":WAN_GP_RENDERER' in src

def test_wangp_uses_seconds_and_runtime_fps():
    src=(ROOT/"app"/"wangp.py").read_text(encoding="utf-8")
    assert '"video_length"' in src
    assert '"force_fps"' in src
    assert 'f"{float(scene.duration):.3f}s"' in src

def test_wangp_fail_closed_without_endpoint(monkeypatch):
    from app import wangp
    monkeypatch.delenv("WANGP_MCP_URL",raising=False)
    monkeypatch.setattr(wangp,"Client",object())
    monkeypatch.setattr(wangp,"streamable_http_client",object())
    monkeypatch.setattr(wangp,"httpx2",object())
    try:
        wangp.WanGPClient()
    except RuntimeError as exc:
        assert "WANGP_MCP_URL" in str(exc)
    else:
        raise AssertionError("WanGP client must fail closed without endpoint")
