from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("VISUAL_RETRIES", "2")))
TIMEOUT = max(15, int(os.getenv("VISUAL_TIMEOUT", "90")))


def _safe_name(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "scene")).strip("-")[:80] or "scene"


def _vehicle(scene: dict) -> str:
    return str(scene.get("vehicle") or os.getenv("CAR_VEHICLE", "automotive vehicle")).strip()


def build_visual_prompt(scene: dict) -> str:
    vehicle = _vehicle(scene)
    subject = str(scene.get("visual_subject") or scene.get("text_en") or "automotive engineering scene").strip()
    component = str(scene.get("technical_component") or "").strip()
    plan = str(scene.get("visual_plan") or "").strip()
    return (
        f"Create a technically accurate automotive editorial still for {vehicle}. "
        f"Scene subject: {subject}. Technical focus: {component}. Visual plan: {plan}. "
        "Preserve the exact vehicle identity and generation when a vehicle is visible; do not substitute another make or model. "
        "Prefer a clean studio/editorial composition, realistic materials, physically plausible engineering, no invented badges, "
        "no readable text, no UI/HUD, no watermark, no diagram labels, no fantasy mechanical parts. "
        "The image is a background plate that will receive a separate local technical overlay."
    )


def _provider_config() -> tuple[str, str, str]:
    """Resolve the production image provider through Odysseus first.

    Direct image-provider settings are retained only as a local-development
    fallback when no Odysseus gateway URL is configured. Production CI therefore
    cannot silently bypass the gateway and expose provider credentials.
    """
    base = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
    gateway_url = f"{base}/api/v1/images/generations" if base else ""
    if gateway_url:
        api_url = gateway_url
        api_key = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
    else:
        api_url = os.getenv("VISUAL_IMAGE_API_URL", "").strip()
        api_key = os.getenv("VISUAL_IMAGE_API_KEY", "").strip()
    model = (
        os.getenv("GEMINI_IMAGE_MODEL", "").strip()
        or os.getenv("VISUAL_IMAGE_MODEL", "").strip()
        or "gemini-3.1-flash-image"
    )
    return api_url, api_key, model


def _decode_provider_image(payload: dict, dst: Path) -> bool:
    data = payload.get("data") if isinstance(payload, dict) else None
    item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
    b64 = item.get("b64_json") or item.get("base64")
    if b64:
        dst.write_bytes(base64.b64decode(b64))
        return dst.stat().st_size > 0
    url = item.get("url") or payload.get("url")
    if url:
        req = urllib.request.Request(str(url), headers={"User-Agent": "faceless-youtube-shorts-n8n/3.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            dst.write_bytes(response.read())
        return dst.stat().st_size > 0
    return False


def _generate(scene: dict, dst: Path) -> bool:
    api_url, api_key, model = _provider_config()
    if not api_url or not api_key or not model:
        return False
    body = {
        "model": model,
        "prompt": build_visual_prompt(scene),
        "size": os.getenv("VISUAL_IMAGE_SIZE", "1536x1024"),
        "n": 1,
        "response_format": "b64_json",
    }
    last: Exception | None = None
    for attempt in range(RETRIES):
        request = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "faceless-youtube-shorts-n8n/3.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            if _decode_provider_image(payload, dst):
                return True
            raise RuntimeError("visual provider returned no image")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last = exc
        if attempt + 1 < RETRIES:
            time.sleep(min(8, 2 ** attempt))
    if last:
        print(f"VISUAL_PROVIDER=FAIL error={last}", flush=True)
    return False


def _pexels(scene: dict, dst: Path) -> bool:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    query = str(scene.get("pexels_query") or "").strip()
    if not key or not query:
        return False
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": query, "per_page": 12, "orientation": "portrait"})
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            search_request = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "faceless-youtube-shorts-n8n/3.0"})
            with urllib.request.urlopen(search_request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            candidates = []
            for video in payload.get("videos", []):
                for item in video.get("video_files", []):
                    link = item.get("link")
                    width = int(item.get("width") or 0)
                    height = int(item.get("height") or 0)
                    if link and width > 0 and height > 0:
                        candidates.append((1 if height >= width else 0, width * height, int(video.get("id") or 0), link))
            if not candidates:
                raise RuntimeError(f"No Pexels video found for query: {query}")
            link = max(candidates, key=lambda x: (x[0], x[1], x[2]))[3]
            download_request = urllib.request.Request(link, headers={"User-Agent": "faceless-youtube-shorts-n8n/3.0"})
            with urllib.request.urlopen(download_request, timeout=TIMEOUT) as response:
                data = response.read()
            if not data:
                raise RuntimeError("Pexels video download returned an empty file")
            dst.write_bytes(data)
            return dst.stat().st_size > 0
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last = exc
            status = getattr(exc, "code", None)
            if status is not None and status not in {408, 429, 500, 502, 503, 504}:
                break
        if attempt + 1 < RETRIES:
            time.sleep(min(8, 2 ** attempt))
    print(f"PEXELS_FALLBACK=FAIL scene={scene.get('scene_number')} attempts={RETRIES} error={last}", flush=True)
    return False


def prepare_scene_visual(scene: dict, index: int, work: Path) -> tuple[Path, str]:
    work.mkdir(parents=True, exist_ok=True)
    dst = work / f"{index:02d}-visual"
    generated = dst.with_suffix(".png")
    provider = os.getenv("VISUAL_PROVIDER", "auto").strip().lower()
    if provider in {"auto", "generated", "image", "odysseus", "gemini"} and _generate(scene, generated):
        print(f"SCENE_VISUAL={index} provider=odysseus-gemini model={_provider_config()[2]} motion=ken_burns", flush=True)
        return generated, "image"
    if provider in {"auto", "pexels", "video"} and _pexels(scene, dst.with_suffix(".mp4")):
        print(f"SCENE_VISUAL={index} provider=pexels motion=live_clip", flush=True)
        return dst.with_suffix(".mp4"), "video"
    raise RuntimeError(f"SCENE_VISUAL_ABORT: no visual provider succeeded for scene {index}")


def write_manifest(scenes: list[dict], records: list[dict]) -> None:
    path = RUN / "visual_manifest.json"
    path.write_text(json.dumps({
        "contract": "Odysseus → Gemini automotive stills first; Pexels real footage fallback",
        "gateway": "odysseus",
        "image_provider": "gemini",
        "provider_order": ["generated", "pexels"],
        "motion": "Ken Burns/parallax for stills; native motion for video fallback",
        "scenes": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["build_visual_prompt", "prepare_scene_visual", "write_manifest"]
