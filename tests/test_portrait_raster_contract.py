from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from app.core import Scene
from app.raster_automotive import render_scene_raster


def _stats(im, box):
    crop=im.crop(box).convert("L")
    stat=ImageStat.Stat(crop)
    edge=ImageStat.Stat(crop.filter(ImageFilter.FIND_EDGES))
    return stat.mean[0], stat.stddev[0], edge.mean[0]


def test_portrait_render_is_native_and_full_frame(tmp_path):
    scene=Scene(1, "نص عربي للاختبار", "لقطة سيارة كاملة مع إضاءة استوديو وتفصيل واضح", "hero", [], 18.0)
    out=tmp_path/"portrait.png"
    render_scene_raster(scene, "سيارة اختبار", out, (1080,1920), camera="front_3q")
    with Image.open(out).convert("RGB") as im:
        assert im.size == (1080,1920)
        bottom=_stats(im,(0,1680,1080,1920))
        center=_stats(im,(80,620,1000,1360))
        assert bottom[0] > 4.0 and bottom[1] > 2.0 and bottom[2] > 1.0
        assert center[1] > 12.0 and center[2] > 1.5


def test_portrait_path_uses_transparent_hero_recomposition():
    source=Path("app/raster_automotive.py").read_text(encoding="utf-8")
    assert "transparent_background=True" in source
    assert "portrait_safe=True" in source
    assert "Native 9:16 composition" in source
