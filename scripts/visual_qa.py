#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
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
REQUIRE_VISION_QA = os.environ.get("REQUIRE_VISION_QA", "true").lower() == "true"
GENERIC = {"nature", "countryside", "landscape", "background", "abstract", "object", "thing", "person", "people", "room", "building", "city", "sky", "scene", "random", "wall"}


def extract_json(text: str) -> dict:
    text = (text or "").strip().replace("\ufeff", "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("model returned no JSON object")
    raw = text[start:end + 1]
    try:
        return json.loads(raw)
    except Exception as first:
        if repair_json:
            try:
                obj = repair_json(raw, return_objects=True)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        raise RuntimeError("invalid model JSON") from first


def post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def frame(video: Path, out: Path, ratio: float) -> None:
    d = max(0.2, duration(video))
    t = max(0.05, min(d - 0.05, d * ratio))
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "5", str(out)],
        check=True,
    )


def contact_sheet(video: Path, out: Path) -> None:
    tmp = []
    for n, ratio in enumerate((0.18, 0.50, 0.82), 1):
        path = out.parent / f"{out.stem}_{n}.jpg"
        frame(video, path, ratio)
        tmp.append(path)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp[0]), "-i", str(tmp[1]), "-i", str(tmp[2]),
         "-filter_complex", "[0:v]scale=540:960[a];[1:v]scale=540:960[b];[2:v]scale=540:960[c];[a][b][c]hstack=inputs=3,scale=1620:960",
         "-frames:v", "1", str(out)],
        check=True,
    )


def gemini(prompt: str, images: list[Path], key: str) -> dict:
    parts = [{"text": prompt}]
    for path in images:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(path.read_bytes()).decode()}})
    payload = post(
        GEMINI_URL,
        {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0, "maxOutputTokens": 2600, "responseMimeType": "application/json"}},
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return extract_json("".join(p.get("text", "") for p in parts if isinstance(p, dict)))


def openrouter(prompt: str, images: list[Path], key: str) -> dict:
    content = [{"type": "text", "text": prompt}]
    for path in images:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()}})
    payload = post(
        OPENROUTER_URL,
        {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 2600},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless YouTube Shorts Visual QA"},
    )
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    text = (choices[0].get("message") or {}).get("content", "")
    if isinstance(text, list):
        text = "".join(str(x.get("text", "")) for x in text if isinstance(x, dict))
    return extract_json(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    args = ap.parse_args()
    run = Path(args.run_dir)
    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    if len(scenes) != 5:
        print("ERROR: exactly 5 scenes required", file=sys.stderr)
        return 2

    qa = run / "visual_qa"
    qa.mkdir(parents=True, exist_ok=True)
    reports = []
    failures = []
    sheets: list[Path] = []

    for i, scene in enumerate(scenes, 1):
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        report = {"scene": i, "text_en": en, "text_ar": ar, "pexels_query": query, "passed": False, "translation_ok": True}
        reports.append(report)
        rendered = run / "scenes" / f"scene_{i}.mp4"
        source = run / "downloads" / f"source_{i}.mp4"
        if not rendered.exists() or not source.exists() or source.stat().st_size < 100000:
            report["reason"] = "missing or suspicious rendered/source footage"
            failures.append({"scene": i, "type": "qa", "reason": report["reason"]})
            continue
        if not query or any(token.lower() in GENERIC for token in query.split()):
            report["reason"] = "generic visual query"
            failures.append({"scene": i, "type": "visual", "reason": report["reason"]})
        if "chameleon" in en.lower() and ("حرباء" not in ar or "القمل" in ar):
            report["translation_ok"] = False
            report["translation_reason"] = "chameleon must translate to حرباء"
            failures.append({"scene": i, "type": "translation", "reason": report["translation_reason"]})
        try:
            sheet = qa / f"scene_{i}_sheet.jpg"
            contact_sheet(rendered, sheet)
            sheets.append(sheet)
        except Exception as exc:
            report["reason"] = f"frame extraction failed: {exc}"
            failures.append({"scene": i, "type": "qa", "reason": report["reason"]})

    prompt = '''You are the strict final publication gate for five YouTube Shorts scenes. Each attached image is a 3-frame contact sheet for one scene, in order 1..5. Compare the actual footage against the concrete visual subject in the scene's Pexels query and the narration. A pass requires the actual main subject to be visibly present and materially relevant. Reject unrelated people, cats, objects, rooms, generic landscapes, or merely similar-looking footage. Also verify that Arabic preserves the English meaning. Return ONLY JSON with exactly five scene objects: {"scenes":[{"scene":1,"visual_match":true,"visual_score":0.95,"translation_ok":true,"reason":"...","translation_reason":"..."},...]}. Score 0.90+ only for a strong direct match; 0.80-0.89 for a clear but less direct match; below 0.80 for weak or unrelated footage.'''
    prompt += "\n" + "\n".join(
        f"SCENE {i}: EN={scene.get('text_en','')} | AR={scene.get('text_ar','')} | QUERY={scene.get('pexels_query','')}"
        for i, scene in enumerate(scenes, 1)
    )

    result = None
    model = "none"
    provider_errors = []

    if len(sheets) == 5 and os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            result = gemini(prompt, sheets, os.environ["GEMINI_API_KEY"].strip())
            model = f"Gemini:{GEMINI_MODEL}"
        except Exception as exc:
            provider_errors.append(f"Gemini: {exc}")
            print(f"Gemini visual QA unavailable: {exc}", file=sys.stderr)

    if result is None and len(sheets) == 5 and os.environ.get("OPENROUTER_API_KEY", "").strip():
        try:
            result = openrouter(prompt, sheets, os.environ["OPENROUTER_API_KEY"].strip())
            model = f"OpenRouter:{OPENROUTER_MODEL}"
        except Exception as exc:
            provider_errors.append(f"OpenRouter: {exc}")
            print(f"OpenRouter visual QA unavailable: {exc}", file=sys.stderr)

    items = result.get("scenes") if isinstance(result, dict) else None
    if not isinstance(items, list) or len(items) != 5:
        result = None

    if result is None:
        if REQUIRE_VISION_QA:
            reason = "No vision provider returned a valid five-scene assessment"
            failures.append({"type": "vision_provider", "reason": reason, "providers": provider_errors})
            for report in reports:
                report["reason"] = reason
                report["passed"] = False
                report["visual_match"] = False
                report["visual_score"] = 0.0
            model = "vision-unavailable-fail-closed"
        else:
            for report in reports:
                report["reason"] = "vision provider unavailable; semantic fallback explicitly enabled"
                report["visual_match"] = True
                report["visual_score"] = 0.80
                report["passed"] = bool(report.get("translation_ok", True))
            model = "explicit-semantic-fallback"
    else:
        by_scene = {}
        for item in items:
            try:
                by_scene[int(item.get("scene"))] = item
            except Exception:
                continue
        if set(by_scene) != {1, 2, 3, 4, 5}:
            failures.append({"type": "vision_provider", "reason": "vision response did not contain all five scenes"})
        for i, report in enumerate(reports, 1):
            item = by_scene.get(i)
            if not item:
                report["reason"] = "missing scene assessment"
                report["passed"] = False
                failures.append({"scene": i, "type": "visual", "reason": report["reason"]})
                continue
            try:
                score = float(item.get("visual_score", 0))
            except Exception:
                score = 0.0
            visual_ok = bool(item.get("visual_match")) and score >= 0.80
            translation_ok = bool(item.get("translation_ok")) and bool(report.get("translation_ok", True))
            report.update({
                "visual_match": bool(item.get("visual_match")),
                "visual_score": score,
                "translation_ok": translation_ok,
                "reason": str(item.get("reason", "")),
                "translation_reason": str(item.get("translation_reason", "")),
                "passed": visual_ok and translation_ok and not any(f.get("scene") == i for f in failures),
            })
            if not visual_ok:
                failures.append({"scene": i, "type": "visual", "score": score, "reason": report["reason"]})
            if not translation_ok:
                failures.append({"scene": i, "type": "translation", "reason": report.get("translation_reason", "model rejected translation")})
            print(f"Scene {i}: {'PASS' if report['passed'] else 'FAIL'} visual={score:.2f} translation={translation_ok} | {report['reason']}", flush=True)

    final = {
        "passed": not failures and len(reports) == 5,
        "model": model,
        "vision_required": REQUIRE_VISION_QA,
        "provider_errors": provider_errors,
        "thresholds": {"visual_score": 0.80, "required_scenes": 5},
        "scene_reports": reports,
        "failures": failures,
    }
    (qa / "report.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Visual QA report written: {qa / 'report.json'}", flush=True)
    if failures:
        print("VISUAL/TRANSLATION QA FAILED — upload must not proceed.", file=sys.stderr)
        return 1
    print("VISUAL/TRANSLATION QA PASSED — all scenes cleared the publication gate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
