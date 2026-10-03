from __future__ import annotations

import re
from pathlib import Path

from .core import RUN, Story
from .wangp import generate_visuals as _generate_wangp_visuals

CAMERAS = ("front_three_quarter","low_front","front_detail","rear_three_quarter","wide_environment","high_three_quarter","side_profile","rear_detail")


def _kind(scene):
    text=(scene.narration+" "+scene.visual_intent).casefold()
    groups={
        "performance":["أداء","قوة","حصان","عزم","تسارع","سرعة"],
        "design":["تصميم","هيكل","شكل","خارجية","ديناميكية"],
        "interior":["مقصورة","داخلية","مقاعد","شاشة","تابلوه"],
        "technology":["تقنية","تقنيات","حساس","كاميرا","مساعدة"],
        "efficiency":["مدى","كفاءة","استهلاك","بطارية","كهربائية"],
        "charging":["شحن","الشحن"],
        "safety":["أمان","فرامل","وسادة","تصادم"],
        "price":["سعر","تكلفة","قيمة"],
    }
    for name,words in groups.items():
        if any(w in text for w in words): return name
    return "hero"


def camera_for_scene(scene_id:int, kind:str)->str:
    return "cockpit_driver_eye" if kind=="interior" else CAMERAS[(scene_id-1)%len(CAMERAS)]


def generate_visuals(story: Story, out_dir: Path=RUN/"scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    _generate_wangp_visuals(story,out_dir)


def _camera(scene_id:int):
    return CAMERAS[(scene_id-1)%len(CAMERAS)]
