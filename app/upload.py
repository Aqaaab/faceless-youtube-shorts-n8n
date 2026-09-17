from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = {"https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"}
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 5000


def service():
    credentials = Credentials(None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], scopes=sorted(SCOPES))
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError("YOUTUBE OAUTH FAILED: refresh token is expired, revoked, or invalid; generate a new offline token with both youtube.upload and youtube.readonly scopes") from exc
    granted=set(credentials.scopes or [])
    missing=sorted(SCOPES-granted)
    if missing: raise RuntimeError("YouTube OAuth token is missing required scopes: "+", ".join(missing))
    return build("youtube","v3",credentials=credentials,cache_discovery=False)


def fingerprint(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _clean_text(value,limit:int)->str:
    text=re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"," ",str(value or "")); text=text.replace("\r\n","\n").replace("\r","\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()[:limit]
def _marker(title:str)->str:
    return " [ACE:"+hashlib.sha256(_clean_text(title,MAX_TITLE_CHARS).casefold().encode("utf-8")).hexdigest()[:12]+"]"
def _final_title(title:str,marker:str)->str:
    base=_clean_text(title,MAX_TITLE_CHARS)
    return base+marker if len(base)+len(marker)<=MAX_TITLE_CHARS else base[:MAX_TITLE_CHARS-len(marker)].rstrip()+marker


def existing_titles(svc,marker:str)->bool:
    channels=svc.channels().list(part="id",mine=True).execute().get("items",[])
    if not channels: raise RuntimeError("YouTube OAuth succeeded but no channel is accessible")
    channel_id=channels[0]["id"]; page_token=None
    while True:
        params={"part":"snippet","channelId":channel_id,"type":"video","maxResults":50}
        if page_token: params["pageToken"]=page_token
        data=svc.search().list(**params).execute()
        if any(marker in item.get("snippet",{}).get("title","") for item in data.get("items",[])): return True
        page_token=data.get("nextPageToken")
        if not page_token:return False


def _require_final_qa(root:Path)->dict:
    report_path=root/"qa_report.json"; master=root/"master_final.mp4"; shorts=[root/"shorts"/f"short_{i}.mp4" for i in range(1,5)]; evidence=[root/"subtitle_burn.json",root/"short_subtitles_burn.json"]; required=[report_path,master,*shorts,*evidence]
    if any(not p.is_file() or p.stat().st_size==0 for p in required): raise RuntimeError("UPLOAD BLOCKED: final artifact, four Shorts, QA report, or subtitle evidence is incomplete")
    try: report=json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise RuntimeError(f"UPLOAD BLOCKED: invalid qa_report.json: {exc}") from exc
    if report.get("passed") is not True: raise RuntimeError("UPLOAD BLOCKED: final QA is not passed")
    score=float(report.get("weighted_score_10",0)); visual=report.get("visual_product_gate",{}); vscore=float(visual.get("average_score",0))
    if score<9.0: raise RuntimeError(f"UPLOAD BLOCKED: final product score {score:.2f}/10 is below 9.0")
    if visual.get("gate_version")!="v4" or vscore<90.0: raise RuntimeError("UPLOAD BLOCKED: strict visual product gate v4 has not passed at >=90/100")
    if report.get("master_sha256")!=fingerprint(master): raise RuntimeError("UPLOAD BLOCKED: master artifact changed after QA")
    actual=[fingerprint(p) for p in shorts]
    if report.get("short_shas",[])!=actual: raise RuntimeError("UPLOAD BLOCKED: one or more Shorts changed after QA")
    return report


def upload(path:Path,title:str,description:str,tags:list[str],svc):
    privacy=os.environ.get("YOUTUBE_PRIVACY_STATUS","public").strip().lower()
    if privacy not in {"public","private","unlisted"}: raise ValueError("YOUTUBE_PRIVACY_STATUS must be public, private or unlisted")
    marker=_marker(title); final_title=_final_title(title,marker)
    if existing_titles(svc,marker): return "SKIPPED_DUPLICATE"
    clean_description=_clean_text(description,MAX_DESCRIPTION_CHARS); clean_tags=[clean for tag in tags or [] if (clean:=_clean_text(tag,500))]
    if len(final_title)>MAX_TITLE_CHARS or not clean_description: raise RuntimeError("UPLOAD BLOCKED: invalid sanitized metadata")
    body={"snippet":{"title":final_title,"description":clean_description,"tags":clean_tags[:500]},"status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":False}}
    request=svc.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(path),mimetype="video/mp4",resumable=True)); response=None
    while response is None: _,response=request.next_chunk()
    return response["id"]


def main():
    root=Path("work"); _require_final_qa(root); state_path=root/"uploaded.json"; state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}; story=json.loads((root/"story.json").read_text(encoding="utf-8")); short_titles=story.get("short_titles")
    if not isinstance(short_titles,list) or len(short_titles)!=4: raise RuntimeError("UPLOAD BLOCKED: exactly four validated Short titles are required")
    svc=service(); items=[(root/"master_final.mp4",story["title"],"long")]+[(root/"shorts"/f"short_{i}.mp4",short_titles[i-1],f"short_{i}") for i in range(1,5)]
    for path,title,kind in items:
        if not path.is_file() or path.stat().st_size==0: raise RuntimeError(f"UPLOAD BLOCKED: missing artifact {path}")
        fp=fingerprint(path); previous=state.get(kind,{})
        if previous.get("fingerprint")==fp and previous.get("video_id"): continue
        video_id=upload(path,title,story["description"],story.get("tags",[]),svc); state[kind]={"fingerprint":fp,"video_id":video_id}; state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(state,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
