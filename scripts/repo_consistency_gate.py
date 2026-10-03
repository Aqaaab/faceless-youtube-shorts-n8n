from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD_FILES={
    "app/blender_automotive.py","app/raster_automotive.py","app/callout_overlay.py",
    "scripts/automotive_model.py","scripts/blender_automotive_scene.py","scripts/build_persistent_asset.py","scripts/temporal_smoke.py",
}
FORBIDDEN=[
    "b"+"lender","raster"+"_"+"automotive",".motion.mp4","scene-render","short"+"_"+"groups",
    "render_scene_blender","visual_product_gate_v3","pex"+"els","generated_"+"still_first",
    "AUTOMOTIVE_RENDER_MOTION","asset_external",
]

def tracked_paths():
    try:
        out=subprocess.run(["git","ls-files"],cwd=ROOT,capture_output=True,text=True,check=True).stdout
    except (OSError,subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git inventory failed: {exc}") from exc
    return [ROOT/p for p in out.splitlines() if p]

def main():
    paths=tracked_paths(); errors=[]
    for rel in OLD_FILES:
        if (ROOT/rel).exists() or rel in {str(p.relative_to(ROOT)) for p in paths}:
            errors.append(f"obsolete tracked file exists: {rel}")
    for path in paths:
        if path.suffix.lower() not in {".py",".yml",".yaml",".json",".md",".txt"}: continue
        try: text=path.read_text(encoding="utf-8",errors="ignore")
        except OSError as exc: errors.append(f"cannot read {path}: {exc}"); continue
        for token in FORBIDDEN:
            if token.casefold() in text.casefold():
                errors.append(f"forbidden legacy token {token!r} in {path}")
    required=["app/wangp.py","app/production_contract.py","app/render.py","app/visual_product_gate.py","app/mp4_visual_gate.py"]
    for rel in required:
        if not (ROOT/rel).is_file(): errors.append(f"required WanGP production file missing: {rel}")
    if errors:
        print("\n".join(errors)); raise SystemExit(1)
    print(json.dumps({"passed":True,"tracked_files":len(paths),"renderer":"wangp","contract":"wangp-v1","legacy_files":0,"forbidden_hits":0},ensure_ascii=False))

if __name__=="__main__": main()
