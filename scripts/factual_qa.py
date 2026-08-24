#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EN_ABSOLUTES = re.compile(
    r"\b(?:always|never|the only|only|forever|immortal|cannot die|never dies|never spoils|never expires|lasts forever|completely safe|100%)\b",
    re.I,
)
AR_ABSOLUTES = re.compile(
    r"(?:دائماً|دائمًا|أبداً|أبدًا|للأبد|إلى الأبد|الوحيد|الوحيدة|الوحيدان|الوحيد الذي|لا يفسد|لا يفسد أبداً|لا يفسد أبدًا|لا تنتهي صلاحيته|لا تنتهي صلاحيته أبداً|لا تنتهي صلاحيته أبدًا|يموت أبداً|يموت أبدًا|آمن تماماً|آمن تمامًا|100٪)",
)
HONEY_MYTH = re.compile(
    r"(?:honey|honeybee|honey bee).*(?:3000|3,000|thousand).*(?:edible|eat|eatable)|(?:3000|3,000|thousand).*(?:edible|eat|eatable).*(?:honey)",
    re.I,
)
UNSUPPORTED_SUPERLATIVES = re.compile(
    r"\b(?:oldest|largest|smallest|fastest|strongest|smartest|first|only|most)\b",
    re.I,
)


def main() -> int:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/run")
    path = run_dir / "job.json"
    if not path.is_file():
        print(f"::error::Missing {path}")
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        print("::error::Factual QA requires exactly 5 scenes")
        return 1

    failures: list[str] = []
    for idx, scene in enumerate(scenes, 1):
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        combined = f"{en} {ar}"

        if EN_ABSOLUTES.search(en):
            failures.append(f"scene {idx}: unsupported absolute claim in English")
        if AR_ABSOLUTES.search(ar):
            failures.append(f"scene {idx}: unsupported absolute claim in Arabic")
        if HONEY_MYTH.search(combined):
            failures.append(f"scene {idx}: archaeological honey claim needs a verified source and must not be stated as established fact")
        if UNSUPPORTED_SUPERLATIVES.search(en):
            failures.append(f"scene {idx}: superlative claim requires explicit verification")

    title = str(data.get("title", ""))
    description = str(data.get("description", ""))
    if EN_ABSOLUTES.search(title) or EN_ABSOLUTES.search(description):
        failures.append("metadata: unsupported absolute claim")

    if failures:
        for failure in failures:
            print(f"::error::Factual QA FAIL — {failure}")
        print("Factual QA: FAIL")
        return 1

    print("Factual QA: PASS — no high-risk absolute, unsupported superlative, or known honey myth pattern detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
