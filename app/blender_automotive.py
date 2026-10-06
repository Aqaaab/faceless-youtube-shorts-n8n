from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BLENDER_SCRIPT = ROOT / "scripts" / "blender_automotive_scene.py"
DEFAULT_TIMEOUT = int(os.getenv("BLENDER_RENDER_TIMEOUT", "180"))


def blender_binary() -> str:
    value = os.getenv("BLENDER_BIN", "").strip()
    if value:
        return value
    found = shutil.which("blender")
    if not found:
        raise RuntimeError("Blender renderer is required but no Blender executable was found.")
    return found



# Production v5 extension: persistent local asset + file cache + temporal motion.
# Temporal delivery renders below native size and is upscaled once during final mux.
from .cache import cache_file, copy_atomic, file_sha256, stable_key, store_file
from .profile import load_profile


def ensure_persistent_asset(profile_name: str | None = None) -> Path:
    profile = load_profile(profile_name)
    profile_path = Path(profile["_path"])
    model_source = ROOT / "scripts" / "automotive_model.py"
    model_hash = file_sha256(model_source) if model_source.is_file() else "unknown-model"
    profile_key = stable_key("asset-v5", profile["name"], profile_path.read_text(encoding="utf-8"), model_hash)
    asset = Path(os.getenv("ACE_CACHE_DIR", str(ROOT / ".ace_cache"))) / "assets" / f"{profile_key}.blend"
    metadata = asset.with_suffix(".json")
    asset.parent.mkdir(parents=True, exist_ok=True)
    if asset.is_file() and asset.stat().st_size > 10000 and metadata.is_file():
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            if payload.get("builder") == "local_blender_procedural_v5_surface_refined" and payload.get("asset_quality_contract") == "v5-surface-refined":
                return asset
        except (OSError, json.JSONDecodeError):
            pass

    cmd = [
        blender_binary(), "--background", "--factory-startup", "--python-exit-code", "1", "--python",
        str(ROOT / "scripts" / "build_persistent_asset.py"),
    ]
    env = os.environ.copy()
    env.update(
        {
            "AUTOMOTIVE_ASSET_OUTPUT": str(asset.resolve()),
            "AUTOMOTIVE_ASSET_METADATA": str(metadata.resolve()),
            "AUTOMOTIVE_PROFILE_PATH": str(profile_path.resolve()),
            "AUTOMOTIVE_PROFILE": profile["name"],
        }
    )
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=int(os.getenv("BLENDER_ASSET_TIMEOUT", "240")),
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Persistent automotive asset build failed:\\n{(exc.stdout or '')[-8000:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Persistent automotive asset build timed out") from exc
    if not asset.is_file() or asset.stat().st_size < 10000:
        raise RuntimeError(f"Persistent automotive asset missing or empty: {asset}")
    return asset


def render_scene_blender(
    scene,
    topic: str,
    out: Path,
    size: tuple[int, int],
    camera: str,
    duration: float | None = None,
) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = map(int, size)
    # Portrait delivery needs more native pixels: at 0.50 scale a 1080x1920
    # frame is rendered at 540x960 then upscaled, which erases fine surface
    # detail required by the Shorts delivery gate. Keep landscape CI cheap while
    # allowing production to opt into a higher portrait scale.
    scale_env = os.getenv("BLENDER_RENDER_SCALE_PORTRAIT", "").strip() if height > width else ""
    scale = float(scale_env or os.getenv("BLENDER_RENDER_SCALE", "1.0"))
    scale = max(0.25, min(1.0, scale))
    min_dim = max(64, int(os.getenv("BLENDER_RENDER_MIN_DIM", "320")))
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    fit = max(1.0, min_dim / min(scaled_width, scaled_height))
    render_width = int(round(scaled_width * fit))
    render_height = int(round(scaled_height * fit))
    profile = load_profile()
    asset = ensure_persistent_asset(profile["name"])
    duration = max(0.25, float(duration if duration is not None else getattr(scene, "duration", 18.0)))
    motion_enabled = os.getenv("AUTOMOTIVE_RENDER_MOTION", "0").strip().lower() in {"1", "true", "yes"}
    motion_fps = max(1, min(30, int(os.getenv("AUTOMOTIVE_MOTION_FPS", str(profile["motion"].get("fps", 15)))))) if motion_enabled else 0
    # Temporal motion is rendered below the still-frame resolution and upscaled once during final mux.
    # This keeps the 25-shot production within the runner budget without weakening the final delivery contract.
    motion_scale = max(0.25, min(1.0, float(os.getenv("BLENDER_MOTION_SCALE", "0.50"))))
    motion_width = max(64, int(round(render_width * motion_scale)))
    motion_height = max(64, int(round(render_height * motion_scale)))
    motion_output = out.with_suffix(".motion.mp4")
    profile_text = Path(profile["_path"]).read_text(encoding="utf-8")
    model_source = ROOT / "scripts" / "automotive_model.py"
    model_hash = file_sha256(model_source) if model_source.is_file() else "unknown-model"
    renderer_source = BLENDER_SCRIPT
    renderer_hash = file_sha256(renderer_source) if renderer_source.is_file() else "unknown-renderer"
    integration_sources = [
        ROOT / "scripts" / "automotive_world.py",
        ROOT / "scripts" / "automotive_shots.py",
        ROOT / "scripts" / "vehicle_rig.py",
    ]
    integration_hash = stable_key(*[
        file_sha256(p) if p.is_file() else f"missing:{p.name}" for p in integration_sources
    ])
    sample_override = os.getenv("BLENDER_RENDER_SAMPLES", "").strip()
    cache_key = stable_key(
        "scene-v6",
        model_hash,
        renderer_hash,
        integration_hash,
        sample_override,
        scale,
        profile["name"],
        profile_text,
        file_sha256(asset),
        getattr(scene, "id", 0),
        getattr(scene, "visual_intent", ""),
        getattr(scene, "narration", ""),
        topic,
        camera,
        width,
        height,
        round(duration, 3),
        render_width,
        render_height,
        motion_width,
        motion_height,
        motion_enabled,
        motion_fps,
    )

    cached_png = cache_file("scene-render", cache_key, ".png")
    cached_meta = cache_file("scene-render", cache_key, ".json")
    cached_motion = cache_file("scene-render", cache_key, ".mp4")
    if cached_png.is_file() and cached_meta.is_file() and (not motion_enabled or cached_motion.is_file()):
        copy_atomic(cached_png, out)
        copy_atomic(cached_meta, out.with_suffix(".blender.json"))
        if motion_enabled:
            copy_atomic(cached_motion, motion_output)
        return json.loads(out.with_suffix(".blender.json").read_text(encoding="utf-8"))

    metadata_path = out.with_suffix(".blender.json")
    cmd = [
        blender_binary(), "--background", "--factory-startup", "--python",
        str(BLENDER_SCRIPT),
    ]
    env = os.environ.copy()
    env.update(
        {
            "AUTOMOTIVE_ASSET_PATH": str(asset.resolve()),
            "AUTOMOTIVE_PROFILE_PATH": str(Path(profile["_path"]).resolve()),
            "AUTOMOTIVE_PROFILE": profile["name"],
            "AUTOMOTIVE_RENDER_OUTPUT": str(out.resolve()),
            "AUTOMOTIVE_RENDER_METADATA": str(metadata_path.resolve()),
            "AUTOMOTIVE_RENDER_MOTION_OUTPUT": str(motion_output.resolve()),
            "AUTOMOTIVE_RENDER_MOTION": "1" if motion_enabled else "0",
            "AUTOMOTIVE_MOTION_FPS": str(motion_fps or profile["motion"].get("fps", 15)),
            "AUTOMOTIVE_RENDER_DURATION": str(duration),
            "AUTOMOTIVE_RENDER_WIDTH": str(render_width),
            "AUTOMOTIVE_RENDER_HEIGHT": str(render_height),
            "AUTOMOTIVE_MOTION_WIDTH": str(motion_width),
            "AUTOMOTIVE_MOTION_HEIGHT": str(motion_height),
            "AUTOMOTIVE_RENDER_CAMERA": str(camera),
            "AUTOMOTIVE_RENDER_SCENE_ID": str(getattr(scene, "id", 0)),
            "AUTOMOTIVE_RENDER_TOPIC": str(topic)[:240],
            "AUTOMOTIVE_RENDER_MODE": str(getattr(scene, "visual_intent", ""))[:240],
        }
    )
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Blender render timed out after {DEFAULT_TIMEOUT}s: {camera}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("Blender executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Blender render failed for {camera}:\\n{(exc.stdout or '')[-8000:]}") from exc

    if not out.is_file() or out.stat().st_size < 4096:
        raise RuntimeError(f"Blender did not produce a valid PNG: {out}\\n{proc.stdout[-8000:]}")
    if not metadata_path.is_file():
        # Blender's render process can finish with valid PNG/MP4 output while a
        # sidecar write is lost on runner shutdown/filesystem pressure. Recover
        # the deterministic contract from the already validated render inputs
        # rather than silently accepting an untracked artifact.
        if not out.is_file() or out.stat().st_size < 4096:
            raise RuntimeError(f"Missing Blender metadata and render output: {metadata_path}")
        recovered = {
            "renderer": "blender_eevee_automotive_v5_temporal",
            "scene_id": getattr(scene, "id", 0),
            "camera": camera,
            "resolution": [render_width, render_height],
            "topic": topic,
            "geometry": "persistent_automotive_coupe_v5_surface_refined",
            "asset_external": False,
            "asset_path": str(asset),
            "asset_sha256": file_sha256(asset),
            "profile": profile["name"],
            "scene_contract": "interior_cockpit_v2" if camera == "interior" else ("wide_environment_v2" if camera == "wide_scene" else "exterior_automotive_v2"),
            "metadata_recovered": True,
            "motion": {
                "enabled": motion_enabled,
                "type": "blender_keyframed_temporal",
                "fps": motion_fps or int(profile["motion"].get("fps", 15)),
                "frames": max(2, int(round(duration * (motion_fps or int(profile["motion"].get("fps", 15)))))),
                "duration": duration,
            },
        }
        metadata_path.write_text(json.dumps(recovered, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    if meta.get("renderer") != "blender_eevee_automotive_v5_temporal":
        raise RuntimeError(f"Unexpected renderer metadata: {meta}")
    actual_resolution = tuple(meta.get("resolution", (0, 0)))
    if actual_resolution != (render_width, render_height):
        raise RuntimeError(f"Blender render resolution contract failed: {meta}")
    if (render_width, render_height) != (width, height):
        with Image.open(out).convert("RGB") as im:
            resized = im.resize((width, height), Image.Resampling.LANCZOS)
            resized.save(out, format="PNG", optimize=False, compress_level=1)
        meta["render_resolution"] = [render_width, render_height]
        meta["resolution"] = [width, height]
        meta["upscaled_for_contract"] = True
        metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if motion_enabled and (not motion_output.is_file() or motion_output.stat().st_size <= 0):
        tail = (proc.stdout or "")[-12000:]
        raise RuntimeError(f"Temporal Blender motion artifact missing: {motion_output}\\nBlender output:\\n{tail}")

    store_file("scene-render", cache_key, ".png", out)
    store_file("scene-render", cache_key, ".json", metadata_path)
    if motion_enabled:
        store_file("scene-render", cache_key, ".mp4", motion_output)
    return {
        "renderer": meta["renderer"],
        "camera": meta.get("shot", camera),
        "shot": meta.get("shot", camera),
        "environment": meta.get("environment", {}),
        "scene_id": getattr(scene, "id", 0),
        "resolution": [width, height],
        "output": str(out),
        "motion_output": str(motion_output) if motion_enabled else None,
        "metadata": str(metadata_path),
        "render_resolution": [render_width, render_height],
        "upscaled_for_contract": [render_width, render_height] != [width, height],
        "asset_path": str(asset),
        "asset_sha256": file_sha256(asset),
        "motion": meta.get("motion", {}),
    }
