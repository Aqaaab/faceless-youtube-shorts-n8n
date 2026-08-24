#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def call_gemini(prompt: str, image_path: Path, key: str) -> dict:
    image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image}},
            ],
        }],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 350,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    text = "".join(
        part.get("text", "")
        for part in (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        if isinstance(part, dict)
    ).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"Gemini returned non-JSON: {text[:300]}")
    return json.loads(text[start:end + 1])


def extract_frame(video: Path, output: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.5", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(output),
    ], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed visual and Arabic QA for generated Shorts scenes")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run = Path(args.run_dir)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("ERROR: GEMINI_API_KEY is required for fail-closed visual QA.", file=sys.stderr)
        return 2

    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    if len(scenes) != 5:
        print("ERROR: visual QA requires exactly 5 scenes.", file=sys.stderr)
        return 2

    qa_dir = run / "visual_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    failures: list[dict] = []

    for index, scene in enumerate(scenes, 1):
        video = run / "scenes" / f"scene_{index}.mp4"
        frame = qa_dir / f"scene_{index}.jpg"
        if not video.exists():
            failures.append({"scene": index, "reason": "missing rendered scene"})
            continue

        extract_frame(video, frame)
        text_en = str(scene.get("text_en", "")).strip()
        text_ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()

        # Deterministic guard for the exact translation failure seen in production.
        lower_en = text_en.lower()
        if "chameleon" in lower_en and "حرباء" not in text_ar:
            failures.append({"scene": index, "reason": "English says chameleon but Arabic translation does not contain حرباء"})
            print(f"Scene {index}: translation FAIL — chameleon must translate to حرباء")
            continue
        if "chameleon" in lower_en and "القمل" in text_ar:
            failures.append({"scene": index, "reason": "incorrect Arabic translation: القمل for chameleon"})
            print(f"Scene {index}: translation FAIL — القمل is not the translation of chameleon")
            continue

        prompt = f'''You are the final publication gate for an automated YouTube Shorts channel.

Narration (English): {text_en}
Arabic subtitle: {text_ar}
Pexels query: {query}
Topic: {job.get("topic", "")}

Inspect the image itself. The visible subject/action must be semantically relevant to the narration, not merely aesthetically similar. If the narration requires a specific animal, object, place, or action, that specific thing must be clearly visible. A random person, cat, generic room, abstract object, or unrelated animal is NOT a match.

Also check the Arabic subtitle against the English narration. It must preserve the same subject, action, quantities, names, and meaning. Do not accept mistranslations or invented words.

Return JSON only:
{{"visual_match": true/false, "visual_score": 0.0-1.0, "translation_ok": true/false, "reason": "brief reason"}}
Set visual_match=true only for a clear direct visual match. Set visual_score >= 0.80 only when the required subject/action is clearly visible.'''

        try:
            result = call_gemini(prompt, frame, key)
            score = float(result.get("visual_score", 0))
            visual_ok = bool(result.get("visual_match")) and score >= 0.80
            translation_ok = bool(result.get("translation_ok"))
            print(
                f"Scene {index}: visual={result.get('visual_match')} score={score:.2f} "
                f"translation={translation_ok} reason={result.get('reason', '')}"
            )
            if not visual_ok:
                failures.append({"scene": index, "reason": f"visual mismatch: {result.get('reason', '')}"})
            if not translation_ok:
                failures.append({"scene": index, "reason": f"Arabic translation mismatch: {result.get('reason', '')}"})
        except Exception as exc:
            failures.append({"scene": index, "reason": f"QA error: {exc}"})

    report = {"passed": not failures, "failures": failures}
    (qa_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if failures:
        print("VISUAL/TRANSLATION QA FAILED — upload must not proceed.", file=sys.stderr)
        return 1

    print("VISUAL/TRANSLATION QA PASSED — all scenes cleared the publication gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
