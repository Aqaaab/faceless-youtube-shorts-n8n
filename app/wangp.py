from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from .cache import scene_key, restore_file, store_file
from .core import RUN, Scene, Story
from .production_contract import (
    LANDSCAPE_ASPECT, LANDSCAPE_DELIVERY, PIPELINE_CONTRACT_VERSION, PORTRAIT_ASPECT,
    PORTRAIT_DELIVERY, WAN_GP_RENDERER,
)

try:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # pragma: no cover
    httpx2 = None
    Client = None
    streamable_http_client = None

MCP_REQUIRED_TOOLS = (
    "wangp_models", "wangp_model", "wangp_generate", "wangp_get_job", "wangp_create_gallery_download",
)


def _json_from_result(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if structured not in (None, {}):
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        raw = text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
    return {}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _find_first(value: Any, keys: tuple[str, ...]) -> Any:
    for item in _walk(value):
        for key in keys:
            if key in item and item[key] not in (None, "", []):
                return item[key]
    return None


def _find_string(value: Any, keys: tuple[str, ...]) -> str | None:
    found = _find_first(value, keys)
    return str(found) if found not in (None, "") else None


def _model_items(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        for key in ("models", "items", "results", "data"):
            if isinstance(value.get(key), list):
                return [x for x in value[key] if isinstance(x, dict)]
    return []


def _metadata(model: dict) -> dict:
    meta = model.get("metadata")
    return meta if isinstance(meta, dict) else model


def _model_type(model: dict) -> str:
    meta = _metadata(model)
    return str(model.get("model_type") or meta.get("model_type") or "").strip()


def _capability(model: dict, name: str) -> bool:
    meta = _metadata(model)
    caps = meta.get("capabilities") if isinstance(meta.get("capabilities"), dict) else {}
    return bool(caps.get(name))


def _media_role(model: dict, role: str) -> bool:
    meta = _metadata(model)
    media = meta.get("media_inputs", {}) if isinstance(meta.get("media_inputs"), dict) else {}
    image = media.get("image", {}) if isinstance(media.get("image"), dict) else {}
    return bool(image.get(role))


def _outputs(model: dict) -> set[str]:
    meta = _metadata(model)
    out = meta.get("main_output") or meta.get("outputs") or []
    return {str(x).casefold() for x in out} if isinstance(out, (list, tuple, set)) else {str(out).casefold()}


def _numeric_resolution(value: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d+)x(\d+)", str(value).strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _collect_values(value: Any, field: str) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() == field.casefold():
                if isinstance(child, str):
                    values.append(child)
                elif isinstance(child, list):
                    values.extend(str(x) for x in child)
                elif isinstance(child, dict):
                    values.extend(_collect_values(child, "choices"))
                    values.extend(_collect_values(child, "allowed"))
            values.extend(_collect_values(child, field))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_values(child, field))
    return values


def _choose_resolution(schema: dict, target: tuple[int, int]) -> str:
    values=[]
    for raw in _collect_values(schema, "resolution") + _collect_values(schema, "choices") + _collect_values(schema, "allowed"):
        parsed=_numeric_resolution(raw)
        if parsed: values.append(parsed)
    unique=list(dict.fromkeys(values))
    if not unique:
        return f"{target[0]}x{target[1]}"
    tw,th=target; target_ratio=tw/th
    scored=[]
    for w,h in unique:
        ratio=w/h; aspect_delta=abs(ratio-target_ratio); size_penalty=abs(w-tw)/max(tw,1)+abs(h-th)/max(th,1)
        scored.append((aspect_delta*10+size_penalty,w,h))
    _,w,h=min(scored)
    return f"{w}x{h}"


def _flag_string(schema: dict, field: str) -> str:
    raw=_collect_values(schema, field)
    for value in raw:
        value=str(value).strip()
        if value and any(flag in value for flag in "ISE"):
            return value
    return raw[0].strip() if raw and str(raw[0]).strip() else ""


def _reference_prompt(topic: str, style: str) -> str:
    return (
        f"Create one photorealistic master reference image for the vehicle/topic: {topic}. "
        f"{style}. Show one complete production vehicle, three-quarter front view, neutral studio background, "
        "accurate automotive proportions, coherent wheels and lights, realistic glass and reflections, no people, no text, no UI, no collage."
    )


def _scene_prompt(story: Story, scene: Scene, style: str, camera: str, previous: bool) -> str:
    continuity = (
        "Begin from the exact visual state suggested by the previous generated shot and preserve the same vehicle identity, paint, wheels, lights and proportions. "
        if previous else
        "Preserve the exact vehicle identity, paint, wheels, lights and proportions from the master reference. "
    )
    return (
        f"Premium cinematic automotive footage for a YouTube scene about {story.topic}. {style}. "
        f"Scene {scene.id}: {scene.visual_intent}. Camera: {camera}. "
        f"{continuity}Vehicle is the primary subject, physically plausible materials and motion, clean composition, realistic lighting, no text, no subtitles, no logos added, no people unless required by the visual intent."
    )


def _camera_for_scene(scene_id: int, visual_mode: str) -> str:
    if visual_mode == "interior":
        return "cockpit_driver_eye"
    return ["front_three_quarter","low_front","front_detail","rear_three_quarter","wide_environment","high_three_quarter","side_profile","rear_detail"][((scene_id-1)%8)]


class WanGPClient:
    def __init__(self):
        self.url=os.getenv("WANGP_MCP_URL","").strip().rstrip("/")
        self.token=os.getenv("WANGP_MCP_TOKEN","").strip()
        self.read_timeout=float(os.getenv("WANGP_READ_TIMEOUT","900"))
        if not self.url:
            raise RuntimeError("WanGP is mandatory: WANGP_MCP_URL is missing")
        if Client is None or streamable_http_client is None or httpx2 is None:
            raise RuntimeError("WanGP MCP client dependency is missing; install requirements.txt")

    async def _connected(self):
        headers={}
        if self.token:
            headers["Authorization"]=f"Bearer {self.token}"
        timeout=httpx2.Timeout(connect=30.0, read=self.read_timeout, write=60.0, pool=60.0)
        http=httpx2.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False)
        transport=streamable_http_client(self.url, http_client=http)
        client=Client(transport)
        return http, client

    async def _call(self, client, name: str, arguments: dict) -> Any:
        result=await client.call_tool(name, arguments=arguments, read_timeout_seconds=self.read_timeout)
        if getattr(result,"is_error",False):
            raise RuntimeError(f"WanGP MCP tool {name} failed: {_json_from_result(result)}")
        return _json_from_result(result)

    async def _session(self):
        http, client=await self._connected()
        await client.__aenter__()
        await http.__aenter__()
        try:
            tools=await client.list_tools()
            names={tool.name for tool in tools.tools}
            missing=[name for name in MCP_REQUIRED_TOOLS if name not in names]
            if missing:
                raise RuntimeError(f"WanGP MCP contract missing tools: {missing}")
            yield client
        finally:
            await client.__aexit__(None,None,None)
            await http.__aexit__(None,None,None)

    async def _open(self):
        http,client=await self._connected()
        await http.__aenter__()
        await client.__aenter__()
        tools=await client.list_tools()
        names={tool.name for tool in tools.tools}
        missing=[name for name in MCP_REQUIRED_TOOLS if name not in names]
        if missing:
            await client.__aexit__(None,None,None); await http.__aexit__(None,None,None)
            raise RuntimeError(f"WanGP MCP contract missing tools: {missing}")
        return http,client

    async def _close(self,http,client):
        await client.__aexit__(None,None,None); await http.__aexit__(None,None,None)

    async def _discover_model(self, client, video: bool) -> tuple[str,dict]:
        requested=os.getenv("WANGP_VIDEO_MODEL_TYPE" if video else "WANGP_REFERENCE_MODEL_TYPE", "").strip()
        data=await self._call(client,"wangp_models",{})
        models=_model_items(data)
        if requested:
            match=next((m for m in models if _model_type(m)==requested),None)
            if match is None: raise RuntimeError(f"Configured WanGP model not available: {requested}")
        else:
            candidates=[]
            for m in models:
                outs=_outputs(m)
                if video:
                    ok="video" in outs and (_capability(m,"image_to_video") or _media_role(m,"reference") or _media_role(m,"start"))
                else:
                    ok="image" in outs and "video" not in outs
                if ok: candidates.append(m)
            if not candidates:
                raise RuntimeError("WanGP model discovery found no compatible model for the requested media type")
            candidates.sort(key=lambda m:("2_2" not in _model_type(m), "i2v" not in _model_type(m), _model_type(m)))
            match=candidates[0]
        model_type=_model_type(match)
        if not model_type: raise RuntimeError("WanGP model discovery returned an entry without model_type")
        schema=await self._call(client,"wangp_model",{"model_type":model_type,"view":"schema"})
        defaults=await self._call(client,"wangp_model",{"model_type":model_type,"view":"defaults"})
        info={"model_type":model_type,"schema":schema,"defaults":defaults,"metadata":_metadata(match)}
        return model_type,info

    async def _wait_result(self, client, value: Any) -> Any:
        job_id=_find_string(value,("job_id","jobId"))
        if not job_id:
            return value
        deadline=time.time()+self.read_timeout*2
        last=value
        while time.time()<deadline:
            await asyncio.sleep(3)
            last=await self._call(client,"wangp_get_job",{"job_id":job_id})
            status=str(_find_first(last,("status","state")) or "").casefold()
            if status in {"completed","complete","done","success","succeeded","finished"}:
                return last
            if status in {"failed","error","cancelled","canceled"}:
                raise RuntimeError(f"WanGP generation job {job_id} failed: {last}")
        raise TimeoutError(f"WanGP generation job {job_id} timed out")

    async def _generate(self, client, settings: dict) -> Any:
        return await self._wait_result(client, await self._call(client,"wangp_generate",{"settings":settings}))

    async def _ensure_reference(self, client, topic: str, style: str) -> str:
        explicit=os.getenv("WANGP_REFERENCE_MEDIA_ID","").strip()
        if explicit:
            return explicit
        path=RUN/"wangp_reference.json"
        if path.is_file():
            try:
                cached=json.loads(path.read_text(encoding="utf-8")); media=str(cached.get("media_id","")).strip()
                if media and cached.get("topic")==topic: return media
            except (OSError,json.JSONDecodeError): pass
        model_type,info=await self._discover_model(client,video=False)
        defaults=_find_first(info["defaults"],("settings","defaults")) or info["defaults"]
        settings=copy.deepcopy(defaults) if isinstance(defaults,dict) else {}
        settings.update({"model_type":model_type,"prompt":_reference_prompt(topic,style),"image_mode":1,"batch_size":1})
        resolution=_choose_resolution(info["schema"],(1024,1024)); settings["resolution"]=resolution
        result=await self._generate(client,settings)
        media=_find_string(result,("media_id","output_media_id","mediaId"))
        if not media:
            raise RuntimeError("WanGP reference generation returned no media_id")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({"media_id":media,"model_type":model_type,"topic":topic,"renderer":WAN_GP_RENDERER},ensure_ascii=False,indent=2),encoding="utf-8")
        await self._download(client,media,RUN/"wangp_reference.png")
        return media

    async def _download(self, client, media_id: str, target: Path) -> None:
        data=await self._call(client,"wangp_create_gallery_download",{"media_id":media_id})
        url=_find_string(data,("url","download_url","href"))
        if not url:
            raise RuntimeError(f"WanGP gallery download returned no URL for media {media_id}")
        target.parent.mkdir(parents=True,exist_ok=True)
        with requests.get(url,stream=True,timeout=self.read_timeout) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(1024*1024):
                    if chunk: handle.write(chunk)
        if target.stat().st_size==0: raise RuntimeError(f"Downloaded WanGP media is empty: {target}")

    async def _generate_scenes(self, story: Story, out_dir: Path, aspect: str, delivery: tuple[int,int], scene_ids: list[int]) -> None:
        http,client=await self._open()
        try:
            style=os.getenv("WANGP_STYLE","premium cinematic automotive editorial, photorealistic vehicle materials")
            reference=await self._ensure_reference(client,story.topic,style)
            model_type,info=await self._discover_model(client,video=True)
            defaults=_find_first(info["defaults"],("settings","defaults")) or info["defaults"]
            defaults=copy.deepcopy(defaults) if isinstance(defaults,dict) else {}
            metadata=info.get("metadata",{}) if isinstance(info.get("metadata"),dict) else {}
            supports_ref=bool(_media_role(info,"reference") or _media_role(info,"single_reference") or _media_role(info,"multiple_references"))
            supports_start=_media_role(info,"start")
            if not supports_ref and not supports_start:
                raise RuntimeError(f"WanGP model {model_type} cannot accept reference/start images; identity continuity cannot be guaranteed")
            model_snapshot={"model_type":model_type,"metadata":metadata,"contract_version":PIPELINE_CONTRACT_VERSION}
            (RUN/"wangp_model.json").write_text(json.dumps(model_snapshot,ensure_ascii=False,indent=2),encoding="utf-8")
            previous_media=None
            for sid in scene_ids:
                scene=next(s for s in story.scenes if s.id==sid)
                visual_mode="interior" if "interior" in (scene.visual_intent+" "+scene.narration).casefold() else "general"
                camera=_camera_for_scene(scene.id,visual_mode)
                prompt=_scene_prompt(story,scene,style,camera,bool(previous_media))
                seed=int(hashlib.sha256(f"{story.topic}|{story.title}|{sid}|{aspect}".encode()).hexdigest()[:8],16)
                key=scene_key(topic=story.topic,profile=os.getenv("AUTOMOTIVE_PROFILE","premium_coupe"),scene_id=sid,duration=float(scene.duration),aspect_ratio=aspect,model_type=model_type,prompt=prompt,reference_id=reference,seed=seed)
                mp4=out_dir/f"scene_{sid:02d}.mp4"; preview=out_dir/f"scene_{sid:02d}.png"; meta_path=out_dir/f"scene_{sid:02d}.json"
                if meta_path.is_file() and mp4.is_file() and preview.is_file():
                    try:
                        cached=json.loads(meta_path.read_text(encoding="utf-8"))
                        if cached.get("cache_key")==key and cached.get("renderer")==WAN_GP_RENDERER:
                            previous_media=str(cached.get("media_id")) or previous_media; continue
                    except (OSError,json.JSONDecodeError): pass
                cached_mp4=RUN.parent/".ace_cache"/"wangp"/f"{key}.mp4"
                if cached_mp4.is_file() and cached_mp4.stat().st_size>0:
                    cached_mp4.parent.mkdir(parents=True,exist_ok=True); mp4.parent.mkdir(parents=True,exist_ok=True); mp4.write_bytes(cached_mp4.read_bytes())
                    subprocess.run(["ffmpeg","-y","-i",str(mp4),"-frames:v","1",str(preview)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    previous_media=None
                    meta={"renderer":WAN_GP_RENDERER,"contract_version":PIPELINE_CONTRACT_VERSION,"scene_id":sid,"duration_requested":float(scene.duration),"aspect_ratio":aspect,"delivery_resolution":list(delivery),"model_type":model_type,"reference_media_id":reference,"seed":seed,"prompt_sha256":hashlib.sha256(prompt.encode("utf-8")).hexdigest(),"cache_key":key,"subject_priority":"vehicle_primary","camera":camera,"visual_family":visual_mode,"continuity_from":"master_reference"}
                    meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
                    continue
                settings=copy.deepcopy(defaults)
                settings.update({"model_type":model_type,"image_mode":0,"prompt":prompt,"resolution":_choose_resolution(info["schema"],delivery),"video_length":f"{float(scene.duration):.3f}s","force_fps":int(os.getenv("WANGP_FPS","15")),"seed":seed})
                if supports_ref:
                    settings["image_refs"]=[reference]
                    mode=_flag_string(info["schema"],"video_prompt_type")
                    if "I" not in mode: mode="I"
                    settings["video_prompt_type"]=mode
                if supports_start:
                    settings["image_start"]=previous_media or reference
                    ip=_flag_string(info["schema"],"image_prompt_type")
                    settings["image_prompt_type"]="S" if "S" in ip else ip
                result=await self._generate(client,settings)
                media=_find_string(result,("media_id","output_media_id","mediaId"))
                if not media: raise RuntimeError(f"WanGP scene {sid} returned no media_id")
                await self._download(client,media,mp4)
                _normalize_video(mp4,float(scene.duration))
                subprocess.run(["ffmpeg","-y","-i",str(mp4),"-frames:v","1",str(preview)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                store_file("wangp",key,".mp4",mp4)
                meta={"renderer":WAN_GP_RENDERER,"contract_version":PIPELINE_CONTRACT_VERSION,"scene_id":sid,"duration_requested":float(scene.duration),"duration_actual":_probe_duration(mp4),"aspect_ratio":aspect,"delivery_resolution":list(delivery),"model_type":model_type,"reference_media_id":reference,"media_id":media,"seed":seed,"prompt_sha256":hashlib.sha256(prompt.encode("utf-8")).hexdigest(),"cache_key":key,"subject_priority":"vehicle_primary","camera":camera,"visual_family":visual_mode,"continuity_from":"previous_scene" if previous_media else "master_reference"}
                meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
                previous_media=media
        finally:
            await self._close(http,client)

    def generate_scenes(self, story: Story, out_dir: Path, aspect: str, delivery: tuple[int,int], scene_ids: list[int] | None=None) -> None:
        selected=scene_ids or [s.id for s in story.scenes]
        asyncio.run(self._generate_scenes(story,out_dir,aspect,delivery,selected))

    def check(self) -> dict:
        async def runner():
            http,client=await self._open()
            try:
                model_type,info=await self._discover_model(client,video=True)
                return {"ok":True,"renderer":WAN_GP_RENDERER,"model_type":model_type,"protocol":getattr(client,"protocol_version",None),"metadata":info.get("metadata",{})}
            finally:
                await self._close(http,client)
        return asyncio.run(runner())


def _probe_duration(path: Path) -> float:
    value=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],check=True,capture_output=True,text=True).stdout.strip()
    return float(value)


def _normalize_video(path: Path, target: float) -> None:
    actual=_probe_duration(path)
    delta=target-actual
    if abs(delta)<=0.20: return
    tmp=path.with_suffix(".normalized.mp4")
    if actual>target:
        cmd=["ffmpeg","-y","-i",str(path),"-t",f"{target:.3f}","-c","copy",str(tmp)]
    else:
        if delta>1.0: raise RuntimeError(f"WanGP output too short: {actual:.2f}s for requested {target:.2f}s")
        cmd=["ffmpeg","-y","-i",str(path),"-vf",f"tpad=stop_mode=clone:stop_duration={delta:.3f}","-t",f"{target:.3f}","-c:v","libx264","-preset","medium","-crf","18","-an",str(tmp)]
    subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True); tmp.replace(path)


def generate_visuals(story: Story, out_dir: Path, scene_ids: list[int] | None=None) -> None:
    WanGPClient().generate_scenes(story,out_dir,LANDSCAPE_ASPECT,LANDSCAPE_DELIVERY,scene_ids)


def generate_vertical_visuals(story: Story, out_dir: Path, scene_ids: list[int]) -> None:
    WanGPClient().generate_scenes(story,out_dir,PORTRAIT_ASPECT,PORTRAIT_DELIVERY,scene_ids)


if __name__ == "__main__":
    print(json.dumps(WanGPClient().check(),ensure_ascii=False,indent=2))
