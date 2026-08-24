#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

PEXELS_URL = "https://api.pexels.com/videos/search"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")


def post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def extract_json(text: str) -> dict:
    raw = (text or "").strip().replace("\ufeff", "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("vision model returned no JSON")
    raw = raw[start:end + 1]
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        from json_repair import repair_json
        value = repair_json(raw, return_objects=True)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    raise RuntimeError("invalid vision JSON")


def run(cmd: list[str], capture: bool = False) -> str:
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if capture else ""


def candidate_frames(video: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    raw_duration = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)], capture=True)
    d = max(float(raw_duration or "0"), 1.0)
    frames = []
    for idx, ratio in enumerate((0.20, 0.50, 0.80), 1):
        t = max(0.05, min(d - 0.05, d * ratio))
        frame = out / f"f{idx}.jpg"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "6", str(frame)])
        frames.append(frame)
    sheet = out / "sheet.jpg"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(frames[0]), "-i", str(frames[1]), "-i", str(frames[2]),
        "-filter_complex", "[0:v]scale=360:640[a];[1:v]scale=360:640[b];[2:v]scale=360:640[c];[a][b][c]hstack=inputs=3",
        "-frames:v", "1", str(sheet)
    ])


def search_candidates(query: str, tmp: Path, api_key: str) -> list[Path]:
    import urllib.parse
    params = urllib.parse.urlencode({"query": query, "orientation": "portrait", "size": "large", "per_page": "12"})
    payload = get(f"{PEXELS_URL}?{params}", {"Authorization": api_key, "Accept": "application/json", "User-Agent": "faceless-youtube-shorts/2.0"})
    results: list[tuple[str, int]] = []
    for video in payload.get("videos", []):
        files = []
        for vf in video.get("video_files", []):
            if vf.get("file_type") == "video/mp4" and vf.get("link") and vf.get("width") and vf.get("height"):
                if int(vf["height"]) >= int(vf["width"]):
                    files.append(vf)
        files.sort(key=lambda x: (x.get("width", 0) * x.get("height", 0)), reverse=True)
        if files:
            results.append((files[0]["link"], int(video.get("id", 0))))
        if len(results) >= 6:
            break
    paths: list[Path] = []
    for idx, (url, vid) in enumerate(results, 1):
        path = tmp / f"candidate_{idx}_{vid or idx}.mp4"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "faceless-youtube-shorts/2.0"})
            with urllib.request.urlopen(request, timeout=120) as r, path.open("wb") as w:
                shutil.copyfileobj(r, w)
            if path.stat().st_size >= 100000:
                paths.append(path)
        except Exception:
            continue
    return paths


def choose_with_gemini(prompt: str, sheets: list[Path], key: str) -> dict:
    parts = [{"text": prompt}]
    for sheet in sheets:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(sheet.read_bytes()).decode()}})
    payload = post(GEMINI_URL, {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0, "maxOutputTokens": 1200, "responseMimeType": "application/json"}}, {"x-goog-api-key": key, "Content-Type": "application/json"})
    text = "".join(str(p.get("text", "")) for p in (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []) if isinstance(p, dict))
    return extract_json(text)


def choose_with_openrouter(prompt: str, sheets: list[Path], key: str) -> dict:
    content = [{"type": "text", "text": prompt}]
    for sheet in sheets:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(sheet.read_bytes()).decode()}})
    payload = post(OPENROUTER_URL, {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 1200}, {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless YouTube Shorts Pexels Candidate Selector"})
    return extract_json(((payload.get("choices") or [{}])[0].get("message") or {}).get("content", ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("visual_subject")
    ap.add_argument("narration")
    ap.add_argument("output")
    args = ap.parse_args()
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        print("PEXELS_API_KEY missing", flush=True)
        return 2
    with tempfile.TemporaryDirectory(prefix="pexels-candidates-") as td:
        tmp = Path(td)
        candidates = search_candidates(args.query, tmp, api_key)
        if not candidates:
            print("No Pexels candidates", flush=True)
            return 1
        sheets: list[Path] = []
        usable: list[Path] = []
        for idx, video in enumerate(candidates, 1):
            cdir = tmp / f"c{idx}"
            try:
                candidate_frames(video, cdir)
                sheet = cdir / "sheet.jpg"
                if sheet.exists():
                    usable.append(video)
                    sheets.append(sheet)
            except Exception:
                continue
        selected = 0
        selection_score = 0.0
        reason = "deterministic-first-candidate"
        provider = "none"
        if sheets:
            prompt = f"""Select the BEST video candidate for a faceless YouTube Short scene. Candidate images are supplied in order 1..{len(sheets)}.\n\nLiteral visual subject: {args.visual_subject}\nNarration: {args.narration}\nSearch query: {args.query}\n\nChoose only a candidate where the literal subject is visibly present and is the dominant/main subject. Do NOT reward generic scenery, unrelated people, rooms, props, or merely similar colors. Historical/abstract ideas must not be invented from unrelated footage. Prefer a clear, close, well-lit view of the subject. Return ONLY JSON: {{\"selected\":1,\"score\":0.95,\"reason\":\"...\"}}. Score 0-1."""
            try:
                if os.environ.get("GEMINI_API_KEY", "").strip():
                    result = choose_with_gemini(prompt, sheets, os.environ["GEMINI_API_KEY"].strip())
                    provider = f"Gemini:{GEMINI_MODEL}"
                elif os.environ.get("OPENROUTER_API_KEY", "").strip():
                    result = choose_with_openrouter(prompt, sheets, os.environ["OPENROUTER_API_KEY"].strip())
                    provider = f"OpenRouter:{OPENROUTER_MODEL}"
                else:
                    result = {}
                selected = int(result.get("selected", 1)) - 1
                selected = max(0, min(selected, len(usable) - 1))
                selection_score = float(result.get("score", 0.0))
                reason = str(result.get("reason", ""))
            except Exception as exc:
                reason = f"vision selector unavailable: {exc}"
        chosen = usable[selected] if usable else candidates[0]
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chosen, args.output)
        meta = Path(args.output).with_suffix(".selection.json")
        meta.write_text(json.dumps({"query": args.query, "visual_subject": args.visual_subject, "selected_index": selected + 1, "candidate_count": len(candidates), "selection_score": selection_score, "provider": provider, "reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Selected Pexels candidate {selected + 1}/{len(candidates)} score={selection_score:.2f} provider={provider}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
