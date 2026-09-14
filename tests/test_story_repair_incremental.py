import json

from app import core


def _scene(scene_id: int, narration: str) -> dict:
    return {
        "id": scene_id,
        "narration": narration,
        "visual_intent": "سيارة فاخرة بزاوية أمامية وإضاءة سينمائية",
        "layout": "hero",
        "callouts": [],
        "duration": 18.0,
    }


def test_invalid_scene_ids_only_target_short_or_empty_narration():
    valid_narration = (
        "هذه جملة عربية تحتوي على كلمات كافية للمشهد الحالي وتشرح التصميم والتقنية والأداء "
        "بطريقة واضحة ومترابطة وتضيف سياقاً مفيداً للمشاهد حول السيارة وتجربتها اليومية وأبرز "
        "تفاصيلها الهندسية دون مبالغة أو تكرار للمعلومات السابقة مع ربط هذه المعلومات بسياق "
        "الحلقة وتسلسل المشاهد بشكل طبيعي ومفهوم"
    )
    data = {"scenes": [_scene(i, valid_narration if i != 3 else "") for i in range(1, 26)]}
    assert core._invalid_scene_ids(data) == [3]


def test_incremental_scene_repair_uses_small_batches(monkeypatch):
    data = {"scenes": [_scene(i, "") for i in range(1, 26)]}
    calls = []

    def fake_ask(system, user, *, timeout=None, max_attempts=None):
        calls.append((user, timeout, max_attempts))
        payload = json.loads(user.split("Scenes to repair:\n", 1)[1])
        repaired_narration = (
            "هذه جملة عربية طويلة بما يكفي لإكمال السرد الخاص بالمشهد مع وصف واضح ومترابط "
            "وتفاصيل مناسبة عن السيارة والتصميم والتقنية والأداء وتجربة القيادة والاستخدام اليومي "
            "بحيث يظل النص صالحاً لعقد المشهد بعد الإصلاح التدريجي دون فقدان السياق."
        )
        return {"scenes": [_scene(item["id"], repaired_narration) for item in payload]}

    monkeypatch.setattr(core, "ask_odysseus", fake_ask)
    core._repair_invalid_scenes_incrementally(data, "موضوع سيارة")

    assert len(calls) == 5
    assert all(len(json.loads(u.split("Scenes to repair:\n", 1)[1])) <= 5 for u, _, _ in calls)
    assert all(timeout <= 60 for _, timeout, _ in calls)
    assert all(attempts == 3 for _, _, attempts in calls)
    assert all(25 <= len(s["narration"].split()) <= 75 for s in data["scenes"])
