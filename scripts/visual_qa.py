#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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
            "maxOutputTokens": 500,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            text = "".join(
                part.get("text", "")
                for part in (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
                if isinstance(part, dict)
            ).strip()
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise RuntimeError(f"Gemini returned non-JSON: {text[:500]}")
            return json.loads(text[start:end + 1])
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            last_error = RuntimeError(f"Gemini HTTP {exc.code}: {detail}")
            if exc.code not in {408, 409, 425, 429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2 * attempt)
    raise RuntimeError(str(last_error or "Gemini QA failed"))


def video_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return max(0.1, float(result.stdout.strip()))


def extract_frame(video: Path, output: Path, timestamp: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{timestamp:.3f}", "-i", str(video),
            "-frames:v", "1", "-q:v", "3", str(output),
        ],
        check=True,
    )


def choose_frame_times(duration: float) -> list[float]:
    # Multiple points reduce false failures caused by an intro/transition frame.
    anchors = [0.20, 0.50, 0.80]
    return [max(0.05, min(duration - 0.05, duration * ratio)) for ratio in anchors]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed visual and Arabic QA for generated Shorts scenes")
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

    for index, scene in enumerate(scenes, 1):
        video = run / "scenes" / f"scene_{index}.mp4"
        frame_dir = qa_dir / f"scene_{index}"
        frame_dir.mkdir(parents=True, exist_ok=True)

        text_en = str(scene.get("text_en", "")).strip()
        text_ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        topic = str(job.get("topic", "")).strip()

        report: dict = {
            "scene": index,
            "text_en": text_en,
            "text_ar": text_ar,
            "pexels_query": query,
            "topic": topic,
            "video": str(video),
            "frames": [],
            "passed": False,
        }

        if not video.exists():
            reason = "missing rendered scene"
            failures.append({"scene": index, "reason": reason})
            report["reason"] = reason
            scene_reports.append(report)
            print(f"Scene {index}: FAIL — {reason}", flush=True)
            continue

        try:
            duration = video_duration(video)
            report["duration_seconds"] = duration
            times = choose_frame_times(duration)
            frame_paths: list[Path] = []
            for frame_no, timestamp in enumerate(times, 1):
                frame = frame_dir / f"frame_{frame_no}.jpg"
                extract_frame(video, frame, timestamp)
                frame_paths.append(frame)
                report["frames"].append({"path": str(frame), "timestamp": timestamp})
        except Exception as exc:
            reason = f"frame extraction failed: {exc}"
            failures.append({"scene": index, "reason": reason})
            report["reason"] = reason
            scene_reports.append(report)
            print(f"Scene {index}: FAIL — {reason}", flush=True)
            continue

        # Deterministic guard for the production translation failure.
        lower_en = text_en.lower()
        if "chameleon" in lower_en:
            if "القمل" in text_ar:
                reason = "incorrect Arabic translation: القمل is not the translation of chameleon; expected حرباء"
                failures.append({"scene": index, "reason": reason})
                report["translation_ok"] = False
                report["translation_reason"] = reason
                report["reason"] = reason
                scene_reports.append(report)
                print(f"Scene {index}: FAIL — {reason}", flush=True)
                continue
            if "حرباء" not in text_ar:
                reason = "English says chameleon but Arabic translation does not contain حرباء"
                failures.append({"scene": index, "reason": reason})
                report["translation_ok"] = False
                report["translation_reason"] = reason
                report["reason"] = reason
                scene_reports.append(report)
                print(f"Scene {index}: FAIL — {reason}", flush=True)
                continue

        prompt = f'''You are the final publication gate for an automated YouTube Shorts channel.

SCENE NARRATION (English): {text_en}
ARABIC SUBTITLE: {text_ar}
PEXELS QUERY REQUESTED: {query}
TOPIC: {topic}

You are receiving three frames from the SAME rendered scene, sampled at different timestamps. Judge the scene using the strongest valid frame, but penalize the result if the visible content is unrelated across the scene.

VISUAL REQUIREMENT:
The visible subject/action must be semantically relevant to the narration, not merely aesthetically similar. If narration requires a specific animal, object, place, person, or action, that specific thing must be clearly visible. A generic person, cat, room, abstract object, random landscape, or unrelated animal is NOT a match.
For abstract scientific statements, judge whether the imagery directly represents the specific subject being discussed. The frame does not need to literally depict an invisible scientific process, but it MUST clearly show the named subject/object/place.

TRANSLATION REQUIREMENT:
The Arabic subtitle must preserve the same subject, action, quantities, names, and meaning. No invented words, substitutions, or dropped key facts.

Return ONLY JSON:
{{
  "visual_match": true/false,
  "visual_score": 0.0-1.0,
  "translation_ok": true/false,
  "best_frame": 1/2/3,
  "reason": "specific concise reason",
  "translation_reason": "specific concise reason"
}}

Set visual_match=true ONLY when a clear direct visual match exists.
Set visual_score >= 0.80 ONLY when the required subject is clearly visible in at least one frame and the scene is not dominated by unrelated imagery.'''

        try:
            result = call_gemini(prompt, frame_paths, key)
            score = float(result.get("visual_score", 0))
            visual_match = bool(result.get("visual_match"))
            translation_ok = bool(result.get("translation_ok"))
            best_frame = result.get("best_frame")
            reason = str(result.get("reason", "No visual reason returned")).strip()
            translation_reason = str(result.get("translation_reason", "No translation reason returned")).strip()

            report.update({
                "visual_match": visual_match,
                "visual_score": score,
                "translation_ok": translation_ok,
                "best_frame": best_frame,
                "reason": reason,
                "translation_reason": translation_reason,
            })

            visual_ok = visual_match and score >= 0.80
            if not visual_ok:
                failures.append({
                    "scene": index,
                    "type": "visual",
                    "reason": reason,
                    "score": score,
                    "best_frame": best_frame,
                    "pexels_query": query,
                    "text_en": text_en,
                })
            if not translation_ok:
                failures.append({
                    "scene": index,
                    "type": "translation",
                    "reason": translation_reason,
                    "text_en": text_en,
                    "text_ar": text_ar,
                })
            report["passed"] = visual_ok and translation_ok

            status = "PASS" if report["passed"] else "FAIL"
            print(
                f"Scene {index}: {status} | visual={visual_match} score={score:.2f} "
                f"translation={translation_ok} best_frame={best_frame} | {reason} | "
                f"translation={translation_reason}",
                flush=True,
            )
        except Exception as exc:
            reason = f"QA error: {exc}"
            failures.append({"scene": index, "type": "qa", "reason": reason})
            report["reason"] = reason
            print(f"Scene {index}: FAIL — {reason}", flush=True)

        scene_reports.append(report)

    report = {
        "passed": not failures,
        "model": GEMINI_MODEL,
        "thresholds": {"visual_score": 0.80, "required_scenes": 5},
        "scene_reports": scene_reports,
        "failures": failures,
    }
    report_path = qa_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
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
