from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
STATE_NAME=".ace_checkpoint.json"; PIPELINE_REVISION="2026-10-wangp-v1"
def signature(topic,profile,pipeline_revision=PIPELINE_REVISION):
    raw=json.dumps({"topic":topic.strip(),"profile":profile.strip(),"revision":pipeline_revision},ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()
def state_path(work): return work/STATE_NAME
def load(work):
    p=state_path(work)
    if not p.is_file(): return {"version":2,"stages":{}}
    try: data=json.loads(p.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): return {"version":2,"stages":{}}
    return data if isinstance(data,dict) else {"version":2,"stages":{}}
def save(work,state):
    work.mkdir(parents=True,exist_ok=True); p=state_path(work); tmp=p.with_suffix(".tmp"); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(p)
def begin(work,topic,profile,reset=False):
    existing=load(work); sig=signature(topic,profile)
    if reset or existing.get("run_signature") not in (None,sig): existing={"version":2,"stages":{}}
    existing.update({"version":2,"pipeline_revision":PIPELINE_REVISION,"run_signature":sig,"topic":topic,"profile":profile,"started_at":existing.get("started_at") or datetime.now(timezone.utc).isoformat(),"updated_at":datetime.now(timezone.utc).isoformat()}); save(work,existing); return existing
def stage_done(state,stage,artifacts):
    info=state.get("stages",{}).get(stage)
    return isinstance(info,dict) and info.get("status")=="done" and all(p.is_file() and p.stat().st_size>0 for p in artifacts)
def mark(state,work,stage,status,artifacts=None,error=None):
    state.setdefault("stages",{})[stage]={"status":status,"artifacts":[str(p) for p in (artifacts or [])],"error":error,"updated_at":datetime.now(timezone.utc).isoformat()}; state["updated_at"]=datetime.now(timezone.utc).isoformat(); save(work,state)
def resume_enabled(): return os.getenv("ACE_RESUME","1").strip().lower() not in {"0","false","no"}
