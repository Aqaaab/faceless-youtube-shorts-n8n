#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from json_repair import repair_json
except Exception:
    repair_json = None

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def call_gemini(prompt: str, image_paths: list[Path], key: str) -> dict:
    parts: list[dict] = [{"text": prompt}]
    for image_path in image_paths:
        image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image}})

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 1400,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}") from exc

    text = "".join(
        part.get("text", "")
        for part in (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        if isinstance(part, dict)
    ).strip()
    if not text:
        raise RuntimeError("Gemini returned empty content")

    # Gemini can return valid JSON cut off at the token limit. json-repair handles
    # minor truncation/formatting issues; otherwise fail closed.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if repair_json is not None:
            try:
                repaired = repair_json(text, return_objects=True)
                if isinstance(repaired, dict):
                    return repaired
            except Exception:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"Gemini returned invalid/truncated JSON: {text[:700]}")


def video_duration(video: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    return max(0.1, float(result.stdout.strip()))


def extract_frame(video: Path, output: Path, timestamp: float) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}",
         "-i", str(video), "-frames:v", "1", "-q:v", "4", str(output)],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed visual and Arabic QA")
    parser.add_argument("run_dir")
    args = parser.parse_args()
    run = Path(args.run_dir)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("ERROR: GEMINI_API_KEY is required for fail-closed visual QA.", file=sys.stderr)
        return 2

    job_path = run / "job.json"
    if not job_path.is_file():
        print(f"ERROR: missing {job_path}", file=sys.stderr)
        return 2
    job = json.loads(job_path.read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    if len(scenes) != 5:
        print("ERROR: visual QA requires exactly 5 scenes.", file=sys.stderr)
        return 2

    qa_dir = run / "visual_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    failures: list[dict] = []
    scene_reports: list[dict] = []
    frame_paths: list[Path] = []

    # Extract one representative frame per scene. One batched Gemini request avoids
    # consuming the free-tier request quota once per scene.
    for index, scene in enumerate(scenes, 1):
        video = run / "scenes" / f"scene_{index}.mp4"
        frame_dir = qa_dir / f"scene_{index}"
        frame_dir.mkdir(parents=True, exist_ok=True)
        text_en = str(scene.get("text_en", "")).strip()
        text_ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        topic = str(job.get("topic", "")).strip()
        report = {"scene": index, "text_en": text_en, "text_ar": text_ar,
                  "pexels_query": query, "topic": topic, "video": str(video),
                  "frames": [], "passed": False}
        scene_reports.append(report)

        if not video.exists():
            reason = "missing rendered scene"
            failures.append({"scene": index, "type": "qa", "reason": reason})
            report["reason"] = reason
            print(f"Scene {index}: FAIL — {reason}", flush=True)
            continue
        try:
            duration = video_duration(video)
            timestamp = max(0.05, min(duration - 0.05, duration * 0.50))
            frame = frame_dir / "frame_1.jpg"
            extract_frame(video, frame, timestamp)
            report["duration_seconds"] = duration
            report["frames"].append({"path": str(frame), "timestamp": timestamp})
            frame_paths.append(frame)
        except Exception as exc:
            reason = f"frame extraction failed: {exc}"
            failures.append({"scene": index, "type": "qa", "reason": reason})
            report["reason"] = reason
            print(f"Scene {index}: FAIL — {reason}", flush=True)

        # Deterministic translation protection.
        lower_en = text_en.lower()
        if "chameleon" in lower_en:
            if "القمل" in text_ar or "حرباء" not in text_ar:
                reason = "incorrect Arabic translation for chameleon; expected حرباء"
                failures.append({"scene": index, "type": "translation", "reason": reason,
                                 "text_en": text_en, "text_ar": text_ar})
                report["translation_ok"] = False
                report["translation_reason"] = reason
                print(f"Scene {index}: FAIL — {reason}", flush=True)

    # If frame extraction itself failed, do not call the model and do not publish.
    if len(frame_paths) != 5:
        report_path = qa_dir / "report.json"
        report_path.write_text(json.dumps({"passed": False, "model": GEMINI_MODEL,
            "thresholds": {"visual_score": 0.80, "required_scenes": 5},
            "scene_reports": scene_reports, "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("VISUAL/TRANSLATION QA FAILED — upload must not proceed.", file=sys.stderr)
        return 1

    scene_context = []
    for i, scene in enumerate(scenes, 1):
        scene_context.append(
            f"SCENE {i}\nEnglish: {scene.get('text_en','')}\nArabic: {scene.get('text_ar','')}\n"
            f"Pexels query: {scene.get('pexels_query','')}\n"
        )

    prompt = f'''You are the final publication gate for an automated YouTube Shorts channel.
You receive exactly one representative frame for each of five rendered scenes, in order.

{chr(10).join(scene_context)}

For each scene, judge whether the visible subject is directly relevant to the narration. A generic person, cat, room, abstract object, unrelated animal, or random landscape is NOT a match when a specific subject is required.
The Arabic subtitle must preserve the same subject, action, quantities, names, and meaning.

Return ONLY one compact JSON object with this exact shape:
{{"scenes":[{{"scene":1,"visual_match":true,"visual_score":0.95,"translation_ok":true,"reason":"...","translation_reason":"..."}},{{"scene":2,"visual_match":false,"visual_score":0.20,"translation_ok":true,"reason":"...","translation_reason":"..."}}]}}
Include exactly five scene objects. visual_score must be 0.0 to 1.0. Score >= 0.80 only for a clear direct visual match.'''

    try:
        result = call_gemini(prompt, frame_paths, key)
        model_scenes = result.get("scenes") if isinstance(result, dict) else None
        if not isinstance(model_scenes, list) or len(model_scenes) != 5:
            raise RuntimeError("Gemini did not return exactly five scene assessments")
        for item in model_scenes:
            try:
                idx = int(item.get("scene"))
                if idx < 1 or idx > 5:
                    raise ValueError
                report = scene_reports[idx - 1]
                score = float(item.get("visual_score", 0))
                visual_match = bool(item.get("visual_match"))
                translation_ok = bool(item.get("translation_ok"))
                reason = str(item.get("reason", "No visual reason returned")).strip()
                translation_reason = str(item.get("translation_reason", "No translation reason returned")).strip()
                report.update({"visual_match": visual_match, "visual_score": score,
                               "translation_ok": translation_ok, "reason": reason,
                               "translation_reason": translation_reason})
                visual_ok = visual_match and score >= 0.80
                if not visual_ok:
                    failures.append({"scene": idx, "type": "visual", "reason": reason,
                                     "score": score, "pexels_query": report["pexels_query"],
                                     "text_en": report["text_en"]})
                if not translation_ok:
                    failures.append({"scene": idx, "type": "translation", "reason": translation_reason,
                                     "text_en": report["text_en"], "text_ar": report["text_ar"]})
                report["passed"] = visual_ok and translation_ok
                status = "PASS" if report["passed"] else "FAIL"
                print(f"Scene {idx}: {status} | visual={visual_match} score={score:.2f} "
                      f"translation={translation_ok} | {reason} | translation={translation_reason}", flush=True)
            except Exception as exc:
                raise RuntimeError(f"invalid scene assessment: {item!r}: {exc}") from exc
    except Exception as exc:
        reason = f"QA model error: {exc}"
        failures.append({"scene": "all", "type": "qa", "reason": reason})
        for report in scene_reports:
            if not report.get("passed"):
                report["reason"] = reason
        print(f"Visual QA model failure: {reason}", file=sys.stderr)

    final_report = {"passed": not failures, "model": GEMINI_MODEL,
                    "thresholds": {"visual_score": 0.80, "required_scenes": 5},
                    "scene_reports": scene_reports, "failures": failures}
    report_path = qa_dir / "report.json"
    report_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Visual QA report written: {report_path}", flush=True)

    if failures:
        print("VISUAL/TRANSLATION QA FAILED — upload must not proceed.", file=sys.stderr)
        for failure in failures:
            print(f"  Scene {failure.get('scene')}: {failure.get('type', 'unknown')} — {failure.get('reason', '')}", file=sys.stderr)
        return 1
    print("VISUAL/TRANSLATION QA PASSED — all scenes cleared the publication gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
