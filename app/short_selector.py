from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat

from .core import RUN, Story

SHORT_MIN_SECONDS = 28.0
SHORT_MAX_SECONDS = 59.0
MIN_CANDIDATES = 30
FINAL_MIN_DISTANCE = 0.055


@dataclass(frozen=True)
class ShortCandidate:
    candidate_id: str
    start_scene: int
    end_scene: int
    start_offset: float
    end_trim: float
    start_time: float
    end_time: float
    duration: float
    hook_score: float
    peak_score: float
    payoff_score: float
    semantic_score: float
    visual_score: float
    topic_score: float
    title: str

    @property
    def scene_ids(self) -> tuple[int, ...]:
        return tuple(range(self.start_scene, self.end_scene + 1))

    @property
    def score(self) -> float:
        return (
            self.hook_score * 0.22
            + self.peak_score * 0.18
            + self.payoff_score * 0.16
            + self.semantic_score * 0.16
            + self.visual_score * 0.13
            + self.topic_score * 0.08
            + self._duration_score() * 0.07
        )

    def _duration_score(self) -> float:
        return max(0.0, 1.0 - abs(self.duration - 40.0) / 40.0)


HOOK = ("لماذا", "كيف", "ما الذي", "المفاجأة", "أهم", "فعلاً", "سر", "هل", "لكن")
PEAK = ("حصان", "عزم", "تسارع", "سرعة", "مدى", "شحن", "أداء", "تقنية", "رقم", "أول", "أفضل")
PAYOFF = ("لذلك", "النتيجة", "الخلاصة", "عملياً", "عمليًا", "في النهاية", "وهنا", "هذا يعني")
SEMANTIC = ("تصميم", "أداء", "تقنية", "أمان", "بطارية", "شحن", "مدى", "مقصورة", "قيمة", "مقارنة")


def _tokens(text: str) -> set[str]:
    return {t for t in re.sub(r"[^\w\u0600-\u06ff]+", " ", text.casefold()).split() if len(t) >= 3 and not t.isdigit()}


def _feature(tokens: set[str], lexicon: tuple[str, ...]) -> float:
    return min(1.0, sum(1 for item in lexicon if item in tokens) / 3.0) if tokens else 0.0


def _scene_times(story: Story) -> dict[int, tuple[float, float]]:
    result, clock = {}, 0.0
    for scene in story.scenes:
        end = clock + float(scene.duration)
        result[scene.id] = (clock, end)
        clock = end
    return result


def _scene_visual_vector(path: Path) -> list[float]:
    with Image.open(path).convert("RGB") as image:
        small = image.resize((16, 16))
        stat = ImageStat.Stat(small)
        pixels = list(small.getdata())
        vector = [v / 255.0 for v in stat.mean]
        for channel in range(3):
            vector.extend(pixel[channel] / 255.0 for pixel in pixels[::4])
        return vector


def _distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _candidate_vector(candidate: ShortCandidate, vectors: dict[int, list[float]]) -> list[float]:
    values = [vectors[sid] for sid in candidate.scene_ids if sid in vectors]
    if not values:
        return []
    return [sum(row[i] for row in values) / len(values) for i in range(len(values[0]))]


def _title(story: Story, start: int, end: int) -> str:
    scene = story.scenes[start - 1]
    seed = re.sub(r"\s+", " ", scene.narration).strip()[:52].rstrip("،,. ")
    title = f"{seed} — {start:02d}-{end:02d}"
    return title[:80].strip()


def build_candidates(story: Story, visual_dir: Path) -> list[ShortCandidate]:
    times = _scene_times(story)
    scene_map = {s.id: s for s in story.scenes}
    vectors = {}
    for sid in scene_map:
        frame = visual_dir / f"scene_{sid:02d}.png"
        if frame.is_file():
            try:
                vectors[sid] = _scene_visual_vector(frame)
            except OSError:
                pass

    candidates: list[ShortCandidate] = []
    variants = (0.0, 1.5, 3.0)
    for start in range(1, len(story.scenes)):
        for span in (1, 2):
            end = start + span
            if end > len(story.scenes):
                continue
            base_start, _ = times[start]
            _, base_end = times[end]
            for start_offset in variants:
                for end_trim in variants:
                    start_time = base_start + start_offset
                    end_time = base_end - end_trim
                    duration = end_time - start_time
                    if not SHORT_MIN_SECONDS <= duration <= SHORT_MAX_SECONDS:
                        continue
                    block = [scene_map[sid] for sid in range(start, end + 1)]
                    text_value = " ".join(s.narration for s in block)
                    toks = _tokens(text_value)
                    first = _tokens(block[0].narration)
                    last = _tokens(block[-1].narration)
                    callouts = sum(bool(s.callouts) for s in block)
                    semantic = _feature(toks, SEMANTIC)
                    topic = _tokens(story.topic + " " + story.title + " " + story.description)
                    topic_score = min(1.0, len(toks & topic) / 8.0) if topic else 0.5
                    visual = min(
                        1.0,
                        0.24 * len(block)
                        + 0.18 * len({str(s.visual_intent).casefold().strip() for s in block})
                        + 0.12 * callouts
                        + 0.18 * len({str(s.layout) for s in block}),
                    )
                    candidates.append(
                        ShortCandidate(
                            candidate_id=f"{start:02d}-{end:02d}-{int(start_offset*10):02d}-{int(end_trim*10):02d}",
                            start_scene=start,
                            end_scene=end,
                            start_offset=round(start_offset, 3),
                            end_trim=round(end_trim, 3),
                            start_time=round(start_time, 3),
                            end_time=round(end_time, 3),
                            duration=round(duration, 3),
                            hook_score=_feature(first, HOOK),
                            peak_score=_feature(toks, PEAK),
                            payoff_score=_feature(last, PAYOFF),
                            semantic_score=semantic,
                            visual_score=visual,
                            topic_score=topic_score,
                            title=_title(story, start, end),
                        )
                    )
    candidates.sort(key=lambda item: (-item.score, item.candidate_id))
    return candidates


def select_best(candidates: list[ShortCandidate], vectors: dict[int, list[float]] | None = None) -> list[ShortCandidate]:
    if len(candidates) < MIN_CANDIDATES:
        raise RuntimeError(f"SHORT CANDIDATE POOL FAILED: only {len(candidates)} valid candidates; required >= {MIN_CANDIDATES}")
    vectors = vectors or {}
    pool = candidates[:40]
    best = None
    best_key = None
    for combo in itertools.combinations(pool, 4):
        scene_sets = [set(c.scene_ids) for c in combo]
        if any(scene_sets[i].intersection(scene_sets[j]) for i in range(4) for j in range(i + 1, 4)):
            continue
        if not vectors:
            min_dist = 0.0
        else:
            sigs = [_candidate_vector(c, vectors) for c in combo]
            min_dist = min((_distance(a, b) for a, b in itertools.combinations(sigs, 2)), default=0.0)
        total = sum(c.score for c in combo)
        key = (min_dist >= FINAL_MIN_DISTANCE, round(min_dist, 6), total)
        if best_key is None or key > best_key:
            best_key, best = key, combo
    if best is None:
        fallback = []
        used: set[int] = set()
        for candidate in candidates:
            scene_ids = set(candidate.scene_ids)
            if used.isdisjoint(scene_ids):
                fallback.append(candidate)
                used.update(scene_ids)
                if len(fallback) == 4:
                    break
        if len(fallback) != 4:
            raise RuntimeError("SHORT SELECTION FAILED: could not find four disjoint candidates")
        best = tuple(fallback)
    return list(best)


def select_shorts(story: Story, visual_dir: Path, manifest_path: Path = RUN / "short_candidates.json") -> dict:
    vectors = {}
    for scene in story.scenes:
        frame = visual_dir / f"scene_{scene.id:02d}.png"
        if frame.is_file():
            vectors[scene.id] = _scene_visual_vector(frame)
    candidates = build_candidates(story, visual_dir)
    selected = select_best(candidates, vectors)
    payload = {
        "pool_size": len(candidates),
        "required_pool_size": MIN_CANDIDATES,
        "selection_thresholds": {
            "short_min_seconds": SHORT_MIN_SECONDS,
            "short_max_seconds": SHORT_MAX_SECONDS,
            "min_predicted_pixel_distance": FINAL_MIN_DISTANCE,
        },
        "candidates": [c.__dict__ | {"scene_ids": list(c.scene_ids), "score": round(c.score, 6)} for c in candidates],
        "selected": [c.__dict__ | {"scene_ids": list(c.scene_ids), "score": round(c.score, 6)} for c in selected],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_selected(manifest_path: Path = RUN / "short_candidates.json") -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = data.get("selected")
    if not isinstance(selected, list) or len(selected) != 4:
        raise RuntimeError("SHORT SELECTION FAILED: manifest does not contain exactly four selected candidates")
    return selected
