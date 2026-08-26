from __future__ import annotations
import ast, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md", "ARCHITECTURE.md", "config/odysseus.json", "config/production.json",
    "config/providers.json", "providers/README.md", "scripts/odysseus.py", "scripts/story.py",
    "scripts/renderer.py", "scripts/production.py", "scripts/qa.py", "scripts/system_gate.py",
    "tests/test_system.py", ".github/workflows/daily-production.yml"
]

def main() -> None:
    errors = []
    for rel in REQUIRED:
        if not (ROOT / rel).is_file(): errors.append(f"missing:{rel}")
    for p in (ROOT / "scripts").glob("*.py"):
        try: ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as e: errors.append(f"syntax:{p}:{e.lineno}:{e.msg}")
    configs = {}
    for rel in ("config/odysseus.json", "config/production.json", "config/providers.json"):
        try: configs[rel] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as e: errors.append(f"json:{rel}:{e}")
    if configs:
        o, p = configs["config/odysseus.json"], configs["config/production.json"]
        if o.get("endpoint_path") != "/api/chat": errors.append("odysseus:endpoint")
        if not o.get("primary") or not o.get("provider_keys_hidden"): errors.append("odysseus:primary-policy")
        if p.get("output", {}).get("shorts", {}).get("count") != 4: errors.append("production:short-count")
        if p.get("output", {}).get("long_video", {}).get("min_seconds") != 420: errors.append("production:min-duration")
        if p.get("output", {}).get("long_video", {}).get("max_seconds") != 900: errors.append("production:max-duration")
    if errors:
        print("SYSTEM_GATE=FAIL")
        print("\n".join(errors))
        raise SystemExit(1)
    print("SYSTEM_GATE=PASS")

if __name__ == "__main__": main()
