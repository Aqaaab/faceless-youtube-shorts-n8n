from __future__ import annotations
import json, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PATH=ROOT/"config"/"automotive_profiles.json"
def load_profile(name=None):
    path=Path(os.getenv("AUTOMOTIVE_PROFILE_PATH",str(DEFAULT_PATH)))
    if not path.is_file(): raise RuntimeError(f"Automotive profile file is missing: {path}")
    data=json.loads(path.read_text(encoding="utf-8")); profiles=data.get("profiles") if isinstance(data,dict) else None
    if not isinstance(profiles,dict): raise RuntimeError("automotive_profiles.json must contain a profiles object")
    profile_name=(name or os.getenv("AUTOMOTIVE_PROFILE","premium_coupe")).strip(); profile=profiles.get(profile_name)
    if not isinstance(profile,dict): raise ValueError(f"Unknown automotive profile: {profile_name}")
    for key in ("visual_style","motion_style","camera_bias"):
        if not isinstance(profile.get(key),str) or not profile[key].strip(): raise RuntimeError(f"Automotive profile field missing or invalid: {key}")
    return {**profile,"name":profile_name,"_path":str(path)}
