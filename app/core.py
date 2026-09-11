from __future__ import annotations
import json, os, re
from dataclasses import dataclass
from pathlib import Path
import requests

BASE=Path(os.getenv("ENGINE_ROOT",".")); RUN=BASE/"work"

@dataclass
class Scene:
    id:int; narration:str; visual_intent:str; layout:str; callouts:list[str]; duration:float

@dataclass
class Story:
    topic:str; title:str; description:str; tags:list[str]; narration:str; scenes:list[Scene]


def _extract_json(text:str)->dict:
    text=text.strip()
    if text.startswith("```"): text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.S)
    return json.loads(text)


def ask_odysseus(system:str,user:str)->dict:
    base=os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/"); key=os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    r=requests.post(f"{base}/api/v1/chat",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"messages":[{"role":"system","content":system},{"role":"user","content":user}]},timeout=180)
    r.raise_for_status(); data=r.json()
    content=data.get("content") or data.get("message",{}).get("content") or data.get("choices",[{}])[0].get("message",{}).get("content")
    if not content: raise RuntimeError("Odysseus returned no model content")
    return _extract_json(content)


def generate_story(topic:str)->Story:
    system='''You are the production Story Engine for a premium Arabic automotive infographic channel. Return JSON only. Create one coherent factual story for the requested car/topic with EXACTLY 25 scenes and no filler. Every scene has id, Arabic narration, visual_intent, layout, callouts and duration. Narration is 25-75 Arabic words and directly drives the visual. Keep scene duration normally 10-35 seconds; target spoken pacing around 1.8-3.0 Arabic words per second so TTS fits the planned duration with only small padding. Never use an ultra-short scene with dense narration. For the eight scenes used by Shorts (1,2,7,8,13,14,19,20), use 14-24 seconds and target roughly 28-60 narration words per scene so each pair naturally stays inside 28-59 seconds. Use only these layouts: hero, technical, spec, comparison, diagram, timeline. Use at least 4 layouts, at least 12 scenes with useful callouts, and at least 20 distinct visual intents. Total duration must be 420-900 seconds. Make visual_intent concrete: identify the vehicle system, camera/composition, infographic element, and on-screen information that should appear. Callouts must be directly supported by the scene narration and must not introduce facts, numbers, ratings, or specifications absent from that narration. Do not invent quantitative claims. Do not mention external media libraries or stock sources. The final visual language is a full-frame premium automotive editorial infographic, not an overlay placed on unrelated footage. Return strong title (20-100 chars), description (120+ chars), and 5+ useful tags.'''
    data=ask_odysseus(system,f"Create the production story for: {topic}")
    scenes=[Scene(int(s["id"]),str(s["narration"]).strip(),str(s["visual_intent"]).strip(),str(s.get("layout","hero")).strip().lower(),list(s.get("callouts",[])),float(s["duration"])) for s in data["scenes"]]
    return Story(topic,str(data["title"]).strip(),str(data["description"]).strip(),list(data.get("tags",[])),str(data.get("narration","")).strip() or " ".join(x.narration for x in scenes),scenes)


def save_story(story:Story,path:Path=RUN/"story.json")->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"topic":story.topic,"title":story.title,"description":story.description,"tags":story.tags,"narration":story.narration,"scenes":[s.__dict__ for s in story.scenes]},ensure_ascii=False,indent=2),encoding="utf-8")
