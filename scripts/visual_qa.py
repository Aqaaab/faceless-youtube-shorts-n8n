#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
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
    raw = (text or "").strip().replace("\ufeff", "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("model returned no JSON")
    raw = raw[start:end + 1]
    try:
        value = json.loads(raw)
        if isinstance(value, dict): return value
    except Exception:
        pass
    if repair_json:
        value = repair_json(raw, return_objects=True)
        if isinstance(value, dict): return value
    raise RuntimeError("invalid model JSON")


def post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def duration(path: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True).strip())


def frame(video: Path, out: Path, ratio: float) -> None:
    d = duration(video)
    t = max(0.05, min(d - 0.05, d * ratio))
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "5", str(out)], check=True)


def contact_sheet(video: Path, out: Path) -> None:
    imgs = []
    for n, ratio in enumerate((0.18, 0.50, 0.82), 1):
        p = out.parent / f"{out.stem}_{n}.jpg"
        frame(video, p, ratio); imgs.append(p)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(imgs[0]), "-i", str(imgs[1]), "-i", str(imgs[2]),
        "-filter_complex", "[0:v]scale=540:960[a];[1:v]scale=540:960[b];[2:v]scale=540:960[c];[a][b][c]hstack=inputs=3,scale=1620:960",
        "-frames:v", "1", str(out)
    ], check=True)


def ask_gemini(prompt: str, images: list[Path], key: str) -> dict:
    parts = [{"text": prompt}] + [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(p.read_bytes()).decode()}} for p in images]
    payload = post(GEMINI_URL, {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0, "maxOutputTokens": 2400, "responseMimeType": "application/json"}}, {"x-goog-api-key": key, "Content-Type": "application/json"})
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return extract_json("".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)))


def ask_openrouter(prompt: str, images: list[Path], key: str) -> dict:
    content = [{"type": "text", "text": prompt}]
    for p in images:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()}})
    payload = post(OPENROUTER_URL, {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 2400}, {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless YouTube Shorts Visual QA"})
    return extract_json(((payload.get("choices") or [{}])[0].get("message") or {}).get("content", ""))


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir"); args = ap.parse_args()
    run = Path(args.run_dir)
    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    failures = []; reports = []; sheets = []

    contract = run / "render_contract.json"
    ass = run / "subtitles" / "subtitles.ass"
    if not contract.exists(): failures.append({"type": "render_contract", "reason": "missing render contract"})
    else:
        c = json.loads(contract.read_text(encoding="utf-8"))
        if c.get("english_overlay") is not False or c.get("arabic_overlay") is not True:
            failures.append({"type": "render_contract", "reason": "render contract does not enforce Arabic-only overlay"})
    if not ass.exists(): failures.append({"type": "subtitle_file", "reason": "missing subtitles.ass"})
    else:
        text = ass.read_text(encoding="utf-8")
        if "Style: EN" in text or re.search(r"Dialogue:.*?,EN,", text):
            failures.append({"type": "subtitle_file", "reason": "English subtitle layer found; Arabic-only overlay required"})
        if "Style: AR" not in text or not re.search(r"Dialogue:.*?,AR,", text):
            failures.append({"type": "subtitle_file", "reason": "Arabic subtitle layer missing"})

    if len(scenes) != 5:
        failures.append({"type": "scene_count", "reason": f"expected 5 scenes, got {len(scenes)}"})

    for i, scene in enumerate(scenes, 1):
        en = str(scene.get("text_en", "")).strip(); ar = str(scene.get("text_ar", "")).strip(); q = str(scene.get("pexels_query", "")).strip(); subject = str(scene.get("visual_subject", "")).strip()
        selection_meta = run / "downloads" / f"source_{i}.selection.json"
        report = {"scene": i, "text_en": en, "text_ar": ar, "visual_subject": subject, "pexels_query": q, "translation_ok": bool(re.search(r"[\u0600-\u06ff]", ar)), "passed": False}
        if selection_meta.exists():
            try: report["candidate_selection"] = json.loads(selection_meta.read_text(encoding="utf-8"))
            except Exception: report["candidate_selection"] = {"error": "invalid selection metadata"}
        reports.append(report)
        rendered = run / "scenes" / f"scene_{i}.mp4"; source = run / "downloads" / f"source_{i}.mp4"
        if not rendered.exists() or not source.exists() or source.stat().st_size < 100000:
            report["reason"] = "missing or suspicious footage"; failures.append({"scene": i, "type": "qa", "reason": report["reason"]}); continue
        if not subject or not q or any(x.lower() in GENERIC for x in q.split()):
            report["reason"] = "weak visual grounding"; failures.append({"scene": i, "type": "visual", "reason": report["reason"]})
        if not report["translation_ok"]:
            failures.append({"scene": i, "type": "translation", "reason": "Arabic translation missing"})
        sheet = run / "visual_qa" / f"scene_{i}_sheet.jpg"; sheet.parent.mkdir(parents=True, exist_ok=True)
        try:
            contact_sheet(rendered, sheet); sheets.append(sheet)
        except Exception as exc:
            report["reason"] = f"frame extraction failed: {exc}"; failures.append({"scene": i, "type": "qa", "reason": report["reason"]})

    prompt = """Strict visual publication gate. Each scene has a literal visual_subject, a Pexels query, narration, and a three-frame sheet. Judge the footage itself, not the search query alone. The literal visual_subject must be clearly visible in the footage and materially relevant to the narrated sentence. It should be the dominant/main subject, not a tiny incidental element. Reject footage that is merely semantically adjacent, has the wrong object, substitutes a related prop, or shows generic people/rooms/landscapes. Do not infer historical age, location, scientific property, or other invisible facts from modern footage. For example, a modern honey jar is not evidence of an ancient Egyptian honey jar unless the narration only asks for a honey jar. Verify Arabic translation preserves the English meaning. Return ONLY JSON: {\"scenes\":[{\"scene\":1,\"visual_match\":true,\"visual_score\":0.95,\"translation_ok\":true,\"reason\":\"...\",\"translation_reason\":\"...\"},...]} with exactly five items. Score visual_match from 0 to 1 based on literal subject presence and narrative relevance; 0.80 is a hard publication threshold."""
    for i, s in enumerate(scenes, 1):
        prompt += f"\nSCENE {i}: SUBJECT={s.get('visual_subject','')} | EN={s.get('text_en','')} | AR={s.get('text_ar','')} | QUERY={s.get('pexels_query','')}"

    result = None; model = "none"; provider_errors = []
    if len(sheets) == 5 and os.environ.get("GEMINI_API_KEY", "").strip():
        try: result = ask_gemini(prompt, sheets, os.environ["GEMINI_API_KEY"].strip()); model = f"Gemini:{GEMINI_MODEL}"
        except Exception as exc: provider_errors.append(f"Gemini: {exc}")
    if result is None and len(sheets) == 5 and os.environ.get("OPENROUTER_API_KEY", "").strip():
        try: result = ask_openrouter(prompt, sheets, os.environ["OPENROUTER_API_KEY"].strip()); model = f"OpenRouter:{OPENROUTER_MODEL}"
        except Exception as exc: provider_errors.append(f"OpenRouter: {exc}")

    items = result.get("scenes") if isinstance(result, dict) else None
    if not isinstance(items, list) or len(items) != 5:
        if REQUIRE_VISION_QA:
            failures.append({"type": "vision_provider", "reason": "No valid five-scene vision assessment", "providers": provider_errors})
            for r in reports: r.update({"visual_match": False, "visual_score": 0.0, "passed": False, "reason": "vision QA unavailable"})
            model = "vision-unavailable-fail-closed"
        else:
            for r in reports: r.update({"visual_match": True, "visual_score": 0.80, "passed": r["translation_ok"]})
            model = "explicit-semantic-fallback"
    else:
        by_scene = {int(x.get("scene")): x for x in items if str(x.get("scene", "")).isdigit()}
        for i, r in enumerate(reports, 1):
            x = by_scene.get(i)
            try: score = float(x.get("visual_score", 0)) if x else 0.0
            except Exception: score = 0.0
            visual_ok = bool(x and x.get("visual_match")) and score >= 0.80
            trans_ok = bool(x and x.get("translation_ok")) and r["translation_ok"]
            r.update({"visual_match": bool(x and x.get("visual_match")), "visual_score": score, "translation_ok": trans_ok, "reason": str((x or {}).get("reason", "")), "translation_reason": str((x or {}).get("translation_reason", "")), "passed": visual_ok and trans_ok})
            if not visual_ok: failures.append({"scene": i, "type": "visual", "score": score, "reason": r["reason"]})
            if not trans_ok: failures.append({"scene": i, "type": "translation", "reason": r["translation_reason"]})

    final = {"passed": not failures and len(reports) == 5, "model": model, "vision_required": REQUIRE_VISION_QA, "provider_errors": provider_errors, "arabic_only_overlay_required": True, "thresholds": {"visual_score": 0.80, "required_scenes": 5}, "candidate_selection_enabled": True, "scene_reports": reports, "failures": failures}
    out = run / "visual_qa" / "report.json"; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Visual QA report written: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
