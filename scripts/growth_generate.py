#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)
BASE_GENERATOR = Path(__file__).with_name("generate_job.py")
GENERIC_QUERY_WORDS = {"nature", "countryside", "landscape", "background", "abstract", "object", "thing", "scene", "person", "people"}
GENERIC_METADATA = {"english", "general", "shorts", "unknown", "miscellaneous"}


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())


def normalize_job(data: dict) -> dict:
    scenes = data.get("scenes") or []
    if len(scenes) != 5:
        raise SystemExit("job.json must contain exactly 5 scenes")

    core_query = " ".join(str(data.get("query") or scenes[0].get("pexels_query") or "").lower().split())
    core_tokens = [t for t in words(core_query) if t not in GENERIC_QUERY_WORDS]
    core = core_tokens[0] if core_tokens else ""

    for index, scene in enumerate(scenes, 1):
        text_en = str(scene.get("text_en", "")).strip()
        text_ar = str(scene.get("text_ar", "")).strip()
        query = " ".join(str(scene.get("pexels_query", "")).lower().split())
        qwords = words(query)
        if not qwords or any(q in GENERIC_QUERY_WORDS for q in qwords):
            # Prefer the article's core subject over abstract landscape footage.
            replacement = core or words(text_en)[0]
            scene["pexels_query"] = replacement
            query = replacement
            qwords = words(query)
        if core and core not in qwords:
            candidate = qwords[:2]
            scene["pexels_query"] = " ".join(([core] + candidate)[:3])
        if "chameleon" in text_en.lower() and ("حرباء" not in text_ar or "القمل" in text_ar):
            raise SystemExit(f"Unsafe Arabic translation in scene {index}: chameleon must translate to حرباء")

    data["script"] = " ".join(str(scene["text_en"]).strip() for scene in scenes)
    data["narration"] = data["script"]
    data["hook"] = str(scenes[0]["text_en"]).strip()
    data["pexels_query"] = str(scenes[0]["pexels_query"]).strip()
    data["provider"] = data.get("provider", "baseline-fallback")

    query = str(data.get("query") or core or "fact").strip()
    topic = str(data.get("topic") or "").strip()
    category = str(data.get("category") or "").strip()
    if topic.lower() in GENERIC_METADATA:
        data["topic"] = query.title()
    if category.lower() in GENERIC_METADATA:
        data["category"] = "Nature"
    if "[" in str(data.get("title", "")) or not str(data.get("title", "")).strip().endswith("#Shorts"):
        data["title"] = f"Did You Know: {data['topic']} #Shorts"

    return data


def main() -> None:
    if not BASE_GENERATOR.is_file():
        raise SystemExit(f"Missing baseline generator: {BASE_GENERATOR}")
    result = subprocess.run([sys.executable, str(BASE_GENERATOR)], env=os.environ.copy())
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    job_path = RUN_DIR / "job.json"
    if not job_path.is_file() or not job_path.stat().st_size:
        raise SystemExit("Baseline generator did not create job.json")

    data = normalize_job(json.loads(job_path.read_text(encoding="utf-8")))
    job_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Growth generation completed through resilient validated generator")


if __name__ == "__main__":
    main()
