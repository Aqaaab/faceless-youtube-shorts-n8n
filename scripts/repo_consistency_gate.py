from __future__ import annotations
import json, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD_FILES=[bytes.fromhex(x).decode() for x in (
    "6170702f626c656e6465725f6175746f6d6f746976652e7079",
    "6170702f7261737465725f6175746f6d6f746976652e7079",
    "6170702f63616c6c6f75745f6f7665726c61792e7079",
    "736372697074732f6175746f6d6f746976655f6d6f64656c2e7079",
    "736372697074732f626c656e6465725f6175746f6d6f746976655f7363656e652e7079",
    "736372697074732f6275696c645f70657273697374656e745f61737365742e7079",
    "736372697074732f74656d706f72616c5f736d6f6b652e7079",
)]
FORBIDDEN=[bytes.fromhex(x).decode() for x in (
    "626c656e646572","7261737465725f6175746f6d6f74697665","2e6d6f74696f6e2e6d7034",
    "7363656e652d72656e646572","73686f72745f67726f757073","72656e6465725f7363656e655f626c656e646572",
    "76697375616c5f70726f647563745f676174655f7633","706578656c73","67656e6572617465645f7374696c6c5f6669727374",
    "4155544f4d4f544956455f52454e4445525f4d4f54494f4e","61737365745f65787465726e616c",
)]

def tracked_paths():
    try:
        out=subprocess.run(["git","ls-files"],cwd=ROOT,capture_output=True,text=True,check=True).stdout
    except (OSError,subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git inventory failed: {exc}") from exc
    return [ROOT/p for p in out.splitlines() if p]

def main():
    paths=tracked_paths(); errors=[]; rel_paths={str(p.relative_to(ROOT)) for p in paths}
    for rel in OLD_FILES:
        if (ROOT/rel).exists() or rel in rel_paths: errors.append("obsolete tracked file exists")
    for path in paths:
        if path.suffix.lower() not in {".py",".yml",".yaml",".json",".md",".txt"}: continue
        try: source=path.read_text(encoding="utf-8",errors="ignore")
        except OSError as exc: errors.append(f"cannot read {path}: {exc}"); continue
        for token in FORBIDDEN:
            if token.casefold() in source.casefold(): errors.append(f"forbidden legacy token in {path}")
    for rel in ("app/wangp.py","app/production_contract.py","app/render.py","app/visual_product_gate.py","app/mp4_visual_gate.py"):
        if not (ROOT/rel).is_file(): errors.append(f"required production file missing: {rel}")
    if errors: print("\n".join(errors)); raise SystemExit(1)
    print(json.dumps({"passed":True,"tracked_files":len(paths),"renderer":"wangp","contract":"wangp-v1","legacy_files":0,"forbidden_hits":0},ensure_ascii=False))
if __name__=="__main__": main()
