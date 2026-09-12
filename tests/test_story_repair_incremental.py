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
    data = {"scenes": [_scene(i, "هذه جملة عربية تحتوي على كلمات كافية للمشهد الحالي" if i != 3 else "") for i in range(1, 26)]}
    assert core._invalid_scene_ids(data) == [3]


def test_incremental_scene_repair_uses_small_batches(monkeypatch):
    data = {"scenes": [_scene(i, "") for i in range(1, 26)]}
    calls = []

    def fake_ask(system, user, *, timeout=None, max_attempts=None):
        calls.append((user, timeout, max_attempts))
        ids = [int(part.split('"')[0]) for part in []]
        # Extract ids from the JSON payload without depending on prompt wording.
        import json
        payload = json.loads(user.split("Scenes to repair:\n", 1)[1])
        return {"scenes": [_scene(item["id"], "هذه جملة عربية طويلة بما يكفي لإكمال السرد الخاص بالمشهد مع وصف واضح ومترابط") for item in payload]}

    monkeypatch.setattr(core, "ask_odysseus", fake_ask)
    core._repair_invalid_scenes_incrementally(data, "موضوع سيارة")

    assert len(calls) == 5
    assert all(len(__import__("json").loads(u.split("Scenes to repair:\n", 1)[1])) <= 5 for u, _, _ in calls)
    assert all(timeout <= 60 for _, timeout, _ in calls)
    assert all(attempts == 1 for _, _, attempts in calls)
    assert all(len(s["narration"].split()) >= 10 for s in data["scenes"])
