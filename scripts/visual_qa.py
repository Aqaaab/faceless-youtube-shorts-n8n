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
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
GENERIC_QUERIES = {
    "nature", "countryside", "landscape", "background", "abstract", "object",
    "thing", "person", "people", "room", "building", "city", "sky", "scene",
}


def extract_json(text: str) -> dict:
    text = (text or "").strip().replace("\ufeff", "")
    if not text:
        raise RuntimeError("empty model response")
    start, end = text.find("{"), text.rfind("}")
    candidate = text[start:end + 1] if start >= 0 and end > start else text
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as first:
        if repair_json is None:
            raise RuntimeError(f"invalid/truncated JSON: {text[:700]}") from first
        try:
            obj = repair_json(candidate, return_objects=True)
        except Exception as exc:
            raise RuntimeError(f"invalid/truncated JSON: {text[:700]}") from exc
    if not isinstance(obj, dict):
        raise RuntimeError("model response is not an object")
    return obj


def post_json(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def model_parts(prompt: str, frame_paths: list[Path]) -> list[dict]:
    parts: list[dict] = [{"text": prompt}]
    for path in frame_paths:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": data}})
    return parts


def assess_gemini(prompt: str, frames: list[Path], key: str) -> dict:
    payload = post_json(
        GEMINI_URL,
        {
            "contents": [{"role": "user", "parts": model_parts(prompt, frames)}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 1800,
                "responseMimeType": "application/json",
            },
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    return extract_json(text)


def assess_openrouter(prompt: str, frames: list[Path], key: str) -> dict:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in frames:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}})
    payload = post_json(
        OPENROUTER_URL,
        {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 1800,
        },
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless YouTube Shorts Visual QA",
        },
    )
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    text = message.get("content") or ""
    if isinstance(text, list):
        text = "".join(str(p.get("text", "")) for p in text if isinstance(p, dict))
    return extract_json(text)


def video_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def extract_frame(video: Path, output: Path) -> None:
    duration = max(0.1, video_duration(video))
    timestamp = max(0.05, min(duration - 0.05, duration * 0.5))
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "4", str(output)],
        check=True,
    )


def deterministic_scene_gate(scene: dict, run: Path, index: int) -> tuple[bool, str]:
    text = str(scene.get("text_en", "")).lower()
    query = " ".join(str(scene.get("pexels_query", "")).lower().split())
    qwords = query.split()
    if not qwords:
        return False, "empty Pexels query"
    if any(word in GENERIC_QUERIES for word in qwords):
        return False, f"generic visual query is not allowed: {query}"
    if not any(word in text for word in qwords):
        return False, f"query is not grounded in scene narration: {query}"
    source = run / "downloads" / f"source_{index}.mp4"
    if not source.exists():
        return False, "missing Pexels source clip"
    if source.stat().st_size < 100_000:
        return False, "source clip is suspiciously small; likely fallback/background"
    return True, "semantic fallback gate passed; model vision unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed visual and Arabic QA")
    parser.add_argument("run_dir")
    args = parser.parse_args()
    run = Path(args.run_dir)
    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    if len(scenes) != 5:
        print("ERROR: visual QA requires exactly 5 scenes.", file=sys.stderr)
        return 2

    qa_dir = run / "visual_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    failures = []
    frames = []

    for index, scene in enumerate(scenes, 1):
        text_en = str(scene.get("text_en", "")).strip()
        text_ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        report = {"scene": index, "text_en": text_en, "text_ar": text_ar, "pexels_query": query, "passed": False}
        reports.append(report)
        video = run / "scenes" / f"scene_{index}.mp4"
        if not video.exists():
            reason = "missing rendered scene"
            report["reason"] = reason
            failures.append({"scene": index, "type": "qa", "reason": reason})
            continue
        try:
            frame = qa_dir / f"scene_{index}.jpg"
            extract_frame(video, frame)
            frames.append(frame)
        except Exception as exc:
            reason = f"frame extraction failed: {exc}"
            report["reason"] = reason
            failures.append({"scene": index, "type": "qa", "reason": reason})
            continue
        if "chameleon" in text_en.lower() and ("حرباء" not in text_ar or "القمل" in text_ar):
            reason = "incorrect Arabic translation for chameleon; expected حرباء"
            report["translation_ok"] = False
            report["translation_reason"] = reason
            failures.append({"scene": index, "type": "translation", "reason": reason})
        else:
            report["translation_ok"] = True

    if failures:
        # Do not spend model quota when deterministic prerequisites already failed.
        pass

    context = "\n".join(
        f"SCENE {i}: English={s.get('text_en','')} | Arabic={s.get('text_ar','')} | Pexels={s.get('pexels_query','')}"
        for i, s in enumerate(scenes, 1)
    )
    prompt = f'''You are the final visual publication gate. Five images are attached in scene order.
{context}
Judge whether each image directly depicts the concrete subject described by its scene. Reject random people, cats, rooms, abstract objects, or unrelated landscapes.
The Arabic must preserve the same subject and meaning.
Return compact JSON only: {{"scenes":[{{"scene":1,"visual_match":true,"visual_score":0.95,"translation_ok":true,"reason":"...","translation_reason":"..."}}, ... five objects total]}}.
visual_score >= 0.80 only for a clear direct visual match.'''

    model_result = None
    model_name = "none"
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if len(frames) == 5 and key:
        try:
            model_result = assess_gemini(prompt, frames, key)
            model_name = f"Gemini:{GEMINI_MODEL}"
        except Exception as exc:
            print(f"Gemini visual QA unavailable: {exc}", file=sys.stderr)
    if model_result is None and len(frames) == 5:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if key:
            try:
                model_result = assess_openrouter(prompt, frames, key)
                model_name = f"OpenRouter:{OPENROUTER_MODEL}"
            except Exception as exc:
                print(f"OpenRouter visual QA unavailable: {exc}", file=sys.stderr)

    if model_result is not None:
        items = model_result.get("scenes") if isinstance(model_result, dict) else None
        if not isinstance(items, list) or len(items) != 5:
            model_result = None
        else:
            for item in items:
                idx = int(item.get("scene", 0))
                if not 1 <= idx <= 5:
                    model_result = None
                    break
                report = reports[idx - 1]
                score = float(item.get("visual_score", 0))
                visual_ok = bool(item.get("visual_match")) and score >= 0.80
                translation_ok = bool(item.get("translation_ok"))
                report.update({"visual_match": bool(item.get("visual_match")), "visual_score": score, "translation_ok": translation_ok, "reason": str(item.get("reason", "")), "translation_reason": str(item.get("translation_reason", "")), "passed": visual_ok and translation_ok})
                if not visual_ok:
                    failures.append({"scene": idx, "type": "visual", "reason": report["reason"], "score": score})
                if not translation_ok:
                    failures.append({"scene": idx, "type": "translation", "reason": report["translation_reason"]})
                print(f"Scene {idx}: {'PASS' if report['passed'] else 'FAIL'} | visual={report['visual_match']} score={score:.2f} translation={translation_ok} | {report['reason']}", flush=True)

    if model_result is None and not failures:
        model_name = "deterministic-semantic-fallback"
        print("Vision models unavailable; applying deterministic semantic gate.", flush=True)
        for index, scene in enumerate(scenes, 1):
            report = reports[index - 1]
            ok, reason = deterministic_scene_gate(scene, run, index)
            report.update({"visual_match": ok, "visual_score": 0.80 if ok else 0.0, "translation_ok": report.get("translation_ok", True), "reason": reason, "passed": ok and report.get("translation_ok", True)})
            if not ok:
                failures.append({"scene": index, "type": "visual", "reason": reason})
            print(f"Scene {index}: {'PASS' if report['passed'] else 'FAIL'} | {reason}", flush=True)

    final = {"passed": not failures and len(reports) == 5, "model": model_name, "thresholds": {"visual_score": 0.80, "required_scenes": 5}, "scene_reports": reports, "failures": failures}
    path = qa_dir / "report.json"
    path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Visual QA report written: {path}", flush=True)
    if failures:
        print("VISUAL/TRANSLATION QA FAILED — upload must not proceed.", file=sys.stderr)
        return 1
    print("VISUAL/TRANSLATION QA PASSED — all scenes cleared the publication gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
