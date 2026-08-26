from __future__ import annotations
import ast, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=["README.md","ARCHITECTURE.md","config/odysseus.json","config/production.json","config/providers.json","scripts/odysseus.py","scripts/story.py","scripts/renderer.py","scripts/production.py","scripts/qa.py","scripts/system_gate.py","tests/test_system.py",".github/workflows/daily-production.yml"]

def main() -> None:
    errors=[]
    for rel in REQUIRED:
        p=ROOT/rel
        if not p.is_file(): errors.append(f"missing:{rel}")
    for p in (ROOT/"scripts").glob("*.py"):
        try: ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as e: errors.append(f"syntax:{p}:{e.lineno}:{e.msg}")
    for rel in ("config/odysseus.json","config/production.json","config/providers.json"):
        try: json.loads((ROOT/rel).read_text(encoding="utf-8"))
        except Exception as e: errors.append(f"json:{rel}:{e}")
    o=json.loads((ROOT/"config/odysseus.json").read_text())
    p=json.loads((ROOT/"config/production.json").read_text())
    if o["endpoint_path"] != "/api/v1/chat": errors.append("odysseus:endpoint")
    if not o["primary"] or not o["provider_keys_hidden"]: errors.append("odysseus:primary-policy")
    if p["output"]["shorts"]["count"] != 4: errors.append("production:short-count")
    if p["output"]["long_video"]["min_seconds"] != 420 or p["output"]["long_video"]["max_seconds"] != 900: errors.append("production:duration")
    if errors:
        print("SYSTEM_GATE=FAIL")
        print("\n".join(errors))
        raise SystemExit(1)
    print("SYSTEM_GATE=PASS")

if __name__ == "__main__": main()
