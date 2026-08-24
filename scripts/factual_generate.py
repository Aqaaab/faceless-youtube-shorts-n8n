#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import generate_job as base
import growth_generate as growth

# Strengthen the generation contract without changing the existing provider stack.
# The model must prefer conservative, well-established facts over dramatic claims.
FACTUAL_RULES = r"""
FACTUAL ACCURACY OVERRIDE:
- Use only facts that are broadly established in reputable scientific or historical references.
- If a detail is uncertain, disputed, anecdotal, or difficult to verify from general knowledge, omit it.
- Never use absolute wording such as "always", "never", "the only", "forever", "immortal", "never spoils", or "never expires".
- Do not claim that a food, animal, material, or process is unique unless that uniqueness is essential and exceptionally well established.
- Avoid exact dates, ages, counts, percentages, rankings, and superlatives unless they are necessary and highly established; prefer "about", "typically", "can", "often", or qualitative wording.
- Do not turn archaeological anecdotes into scientific certainty. In particular, do not state that 3,000-year-old honey was definitely safe or edible; instead explain the well-established preservation mechanism of mature honey.
- Distinguish preservation from guaranteed safety: honey can remain stable for a very long time under suitable conditions, but do not say it "never spoils" or is "safe forever".
- Do not make medical, nutritional, toxicological, or safety claims unless they are conservative and well established.
- The Arabic translation must preserve every factual qualifier in English. Never strengthen a cautious English statement into an absolute Arabic statement.
""".strip()


def main() -> None:
    base.PROMPT = base.PROMPT + "\n\n" + FACTUAL_RULES
    base.main()

    path = Path(base.RUN_DIR) / "job.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data = growth.normalize(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Factual generation completed: conservative claims + Arabic qualifier preservation")


if __name__ == "__main__":
    main()
