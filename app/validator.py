from __future__ import annotations

import re
from pathlib import Path
import json

from .production_contract import (
    SCENE_COUNT, SCENE_IDS, DEFAULT_SCENE_DURATION, SCENE_DURATION_MIN, SCENE_DURATION_MAX,
    SHORT_MIN_SECONDS, SHORT_MAX_SECONDS, SHORT_DELIVERY_COUNT, SHORT_CANDIDATE_MINIMUM,
)

MIN_LONG, MAX_LONG = 420.0, 900.0
MIN_WORDS, MAX_WORDS = 25, 75
ALLOWED_LAYOUTS = {"hero", "technical", "spec", "comparison", "diagram", "timeline"}
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
DIGIT_RE = re.compile(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*")


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(str(text)))


def _numeric_tokens(text: str) -> list[str]:
    return DIGIT_RE.findall(str(text))


def _lexical_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\u0600-\u06ff]+", " ", str(text).casefold())
    return {x for x in cleaned.split() if len(x) >= 3 and not x.isdigit()}


def _validate_callouts(callouts, narration: str, sid: int) -> list[str]:
    errors=[]
    n_numbers=set(_numeric_tokens(narration)); n_words=_lexical_tokens(narration)
    for callout in callouts:
        if not isinstance(callout,str) or not callout.strip():
            errors.append(f"scene {sid} callouts must contain non-empty strings"); continue
        value=callout.strip()
        for token in _numeric_tokens(value):
            if token not in n_numbers: errors.append(f"scene {sid} callout introduces unsupported numeric token: {token}")
        words=_lexical_tokens(value)
        if words and n_words and not (words & n_words):
            errors.append(f"scene {sid} callout is not grounded in narration: {value}")
    return errors


def _validate_short_titles(data: dict, errors: list[str]) -> None:
    titles=data.get("short_titles")
    if not isinstance(titles,list) or len(titles)!=SHORT_DELIVERY_COUNT:
        errors.append(f"exactly {SHORT_DELIVERY_COUNT} short_titles are required"); return
    normalized=[]
    for i,title in enumerate(titles,1):
        value=str(title).strip(); normalized.append(value.casefold())
        if not 20 <= len(value) <= 80: errors.append(f"short title {i} must be 20-80 characters")
        if not _has_arabic(value): errors.append(f"short title {i} must contain Arabic text")
    if len(set(normalized)) != SHORT_DELIVERY_COUNT: errors.append("Short titles must be unique")


def validate_story_data(data: dict) -> bool:
    if not isinstance(data,dict): raise AssertionError("STORY VALIDATION FAILED: root payload must be an object")
    errors=[]; scenes=data.get("scenes")
    if not isinstance(scenes,list): raise AssertionError("STORY VALIDATION FAILED: scenes must be a list")
    if len(scenes)!=SCENE_COUNT: errors.append(f"scene count must be exactly {SCENE_COUNT}, got {len(scenes)}")
    ids=[s.get("id") if isinstance(s,dict) else None for s in scenes]
    if ids!=list(SCENE_IDS): errors.append(f"scene ids must be exactly {list(SCENE_IDS)}, got {ids}")
    durations=[]; layouts=set(); intents=set(); callout_scenes=0; aggregate=[]
    for index,scene in enumerate(scenes,1):
        if not isinstance(scene,dict): errors.append(f"scene {index} must be an object"); continue
        sid=scene.get("id",index)
        try: duration=float(scene.get("duration",0))
        except (TypeError,ValueError): duration=0; errors.append(f"scene {sid} duration is not numeric")
        durations.append(duration)
        if not SCENE_DURATION_MIN<=duration<=SCENE_DURATION_MAX: errors.append(f"scene {sid} duration {duration:.2f}s outside {SCENE_DURATION_MIN:g}-{SCENE_DURATION_MAX:g}s")
        narration=str(scene.get("narration"," ")).strip(); intent=str(scene.get("visual_intent","")).strip(); layout=str(scene.get("layout","")).strip().lower()
        aggregate.append(narration)
        if not MIN_WORDS<=_words(narration)<=MAX_WORDS: errors.append(f"scene {sid} narration must be {MIN_WORDS}-{MAX_WORDS} words")
        if not _has_arabic(narration): errors.append(f"scene {sid} narration must contain Arabic")
        if _words(intent)<4: errors.append(f"scene {sid} visual_intent is too short")
        if layout not in ALLOWED_LAYOUTS: errors.append(f"scene {sid} unsupported layout '{layout}'")
        layouts.add(layout); intents.add(intent.casefold())
        callouts=scene.get("callouts",[])
        if not isinstance(callouts,list): errors.append(f"scene {sid} callouts must be a list")
        else:
            if len(callouts)>5: errors.append(f"scene {sid} has more than 5 callouts")
            if callouts: callout_scenes += 1; errors.extend(_validate_callouts(callouts,narration,int(sid) if str(sid).isdigit() else index))
    total=sum(durations)
    if not MIN_LONG<=total<=MAX_LONG: errors.append(f"planned duration {total:.2f}s outside {MIN_LONG:g}-{MAX_LONG:g}s")
    if len(layouts)<4: errors.append("layout diversity too low")
    if callout_scenes<12: errors.append("callout coverage too low")
    if len(intents)<20: errors.append("visual intent diversity too low")
    title=str(data.get("title","")).strip(); description=str(data.get("description","")).strip(); tags=data.get("tags",[])
    if not title or not 20<=len(title)<=100: errors.append("title must be 20-100 characters")
    if len(description)<120: errors.append("description must be at least 120 characters")
    if not isinstance(tags,list) or len([x for x in tags if str(x).strip()])<5: errors.append("at least 5 non-empty tags are required")
    aggregate_text=str(data.get("narration","")).strip() or " ".join(aggregate)
    if _words(aggregate_text)<200: errors.append("aggregate narration is too short")
    _validate_short_titles(data,errors)
    if errors: raise AssertionError("STORY VALIDATION FAILED: "+"; ".join(errors))
    return True


def validate_story(path: Path=Path("work/story.json"))->bool:
    if not path.exists(): raise AssertionError(f"story file missing: {path}")
    try: data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise AssertionError(f"STORY VALIDATION FAILED: invalid story JSON: {exc}") from exc
    return validate_story_data(data)


def validate_short_selection(data: dict)->bool:
    if not isinstance(data,dict): raise AssertionError("SHORT SELECTION FAILED: root payload must be an object")
    selected=data.get("selected"); pool=int(data.get("pool_size",0) or 0)
    if not isinstance(selected,list) or len(selected)!=SHORT_DELIVERY_COUNT: raise AssertionError("SHORT SELECTION FAILED: expected exactly four selected candidates")
    if pool<SHORT_CANDIDATE_MINIMUM: raise AssertionError(f"SHORT SELECTION FAILED: candidate pool {pool} < {SHORT_CANDIDATE_MINIMUM}")
    sets=[]
    for i,item in enumerate(selected,1):
        if not isinstance(item,dict): raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} malformed")
        try: duration=float(item["duration"]); ids={int(x) for x in item["scene_ids"]}; start=float(item["start_time"]); end=float(item["end_time"])
        except (KeyError,TypeError,ValueError) as exc: raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} malformed: {exc}") from exc
        if not SHORT_MIN_SECONDS<=duration<=SHORT_MAX_SECONDS: raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} duration outside 28-59s")
        if not ids or start>=end: raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} invalid timing")
        if not all(1<=sid<=SCENE_COUNT for sid in ids): raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} has invalid scene id")
        if not 20<=len(str(item.get("title","")).strip())<=80 or not _has_arabic(str(item.get("title","")).strip()): raise AssertionError(f"SHORT SELECTION FAILED: candidate {i} title invalid")
        sets.append(ids)
    for i in range(4):
        for j in range(i+1,4):
            if sets[i] & sets[j]: raise AssertionError(f"SHORT SELECTION FAILED: candidates {i+1} and {j+1} overlap scenes")
    return True
