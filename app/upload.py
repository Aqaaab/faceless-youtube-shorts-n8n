from __future__ import annotations
import hashlib,json,os,re
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from .retry import retry_call

SCOPES={"https://www.googleapis.com/auth/youtube.upload","https://www.googleapis.com/auth/youtube.readonly"}
MAX_TITLE_CHARS=100; MAX_DESCRIPTION_CHARS=5000

def _transient_youtube_error(exc):
    if isinstance(exc,HttpError):
        status=getattr(exc.resp,"status",0); return status==429 or status>=500
    return isinstance(exc,(OSError,TimeoutError))

def service():
    credentials=Credentials(None,refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],token_uri="https://oauth2.googleapis.com/token",client_id=os.environ["YOUTUBE_CLIENT_ID"],client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],scopes=sorted(SCOPES))
    credentials.refresh(Request())
    missing=sorted(SCOPES-set(credentials.scopes or []))
    if missing: raise RuntimeError("YouTube OAuth token is missing required scopes: "+", ".join(missing))
    return build("youtube","v3",credentials=credentials,cache_discovery=False)

def fingerprint(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _clean_text(value,limit): return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"," ",str(value or "")).replace("\r\n","\n").replace("\r","\n").strip()[:limit]
def _marker(title): return " [ACE:"+hashlib.sha256(_clean_text(title,MAX_TITLE_CHARS).casefold().encode()).hexdigest()[:12]+"]"
def _final_title(title,marker):
    base=_clean_text(title,MAX_TITLE_CHARS)
    return base+marker if len(base)+len(marker)<=MAX_TITLE_CHARS else base[:MAX_TITLE_CHARS-len(marker)].rstrip()+marker

def existing_titles(svc,marker):
    channels=svc.channels().list(part="id",mine=True).execute().get("items",[])
    if not channels: raise RuntimeError("YouTube OAuth succeeded but no channel is accessible")
    page_token=None
    while True:
        params={"part":"snippet","channelId":channels[0]["id"],"type":"video","maxResults":50}
        if page_token: params["pageToken"]=page_token
        data=svc.search().list(**params).execute()
        if any(marker in item.get("snippet",{}).get("title","") for item in data.get("items",[])): return True
        page_token=data.get("nextPageToken")
        if not page_token: return False

def _require_final_qa(root):
    report_path=root/"qa_report.json"; master=root/"master_final.mp4"; shorts=[root/"shorts"/f"short_{i}.mp4" for i in range(1,5)]
    evidence=[root/"subtitle_burn.json",root/"short_subtitles_burn.json",root/"visual_product_gate.json",root/"mp4_visual_product_gate.json",root/"arabic_font_gate.json",root/"short_candidates.json",root/"thumbnail.jpg"]
    required=[report_path,master,*shorts,*evidence]
    if any(not path.is_file() or path.stat().st_size==0 for path in required): raise RuntimeError("UPLOAD BLOCKED: final artifact, Shorts, QA report or evidence incomplete")
    try: report=json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise RuntimeError(f"UPLOAD BLOCKED: invalid qa_report.json: {exc}") from exc
    if report.get("passed") is not True: raise RuntimeError("UPLOAD BLOCKED: final QA is not passed")
    if float(report.get("weighted_score_10",0))<9.0: raise RuntimeError("UPLOAD BLOCKED: final product score below 9.0")
    visual=report.get("visual_product_gate",{}); mp4=report.get("mp4_visual_product_gate",{})
    if visual.get("passed") is not True: raise RuntimeError("UPLOAD BLOCKED: WanGP visual gate did not pass")
    if mp4.get("passed") is not True: raise RuntimeError("UPLOAD BLOCKED: MP4 gate did not pass")
    if report.get("renderer")!="wangp" or report.get("renderer_contract")!="wangp-v1": raise RuntimeError("UPLOAD BLOCKED: renderer contract mismatch")
    if report.get("master_sha256")!=fingerprint(master): raise RuntimeError("UPLOAD BLOCKED: master changed after QA")
    if report.get("short_shas")!=[fingerprint(path) for path in shorts]: raise RuntimeError("UPLOAD BLOCKED: Shorts changed after QA")
    return report

def upload(path,title,description,tags,svc):
    privacy=os.environ.get("YOUTUBE_PRIVACY_STATUS","public").strip().lower()
    if privacy not in {"public","private","unlisted"}: raise ValueError("invalid YOUTUBE_PRIVACY_STATUS")
    marker=_marker(title)
    if existing_titles(svc,marker): return "SKIPPED_DUPLICATE"
    body={"snippet":{"title":_final_title(title,marker),"description":_clean_text(description,MAX_DESCRIPTION_CHARS),"tags":[_clean_text(tag,500) for tag in tags or [] if _clean_text(tag,500)]},"status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":False}}
    request=svc.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(path),mimetype="video/mp4",resumable=True))
    def send():
        response=None
        while response is None: _,response=request.next_chunk()
        return response
    response=retry_call(send,attempts=int(os.getenv("YOUTUBE_UPLOAD_RETRY_ATTEMPTS","3")),base_delay=2.0,retry_if=_transient_youtube_error,label=f"YouTube upload ({path.name})")
    return response["id"]

def set_thumbnail(svc,video_id,thumbnail):
    if not thumbnail.is_file() or thumbnail.stat().st_size==0: raise RuntimeError("UPLOAD BLOCKED: thumbnail is missing")
    retry_call(lambda:svc.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(str(thumbnail),mimetype="image/jpeg",resumable=False)).execute(),attempts=3,base_delay=2.0,retry_if=_transient_youtube_error,label="YouTube thumbnail upload")

def main():
    root=Path("work"); _require_final_qa(root)
    state_path=root/"uploaded.json"; state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    story=json.loads((root/"story.json").read_text(encoding="utf-8")); titles=story.get("short_titles")
    if not isinstance(titles,list) or len(titles)!=4: raise RuntimeError("UPLOAD BLOCKED: exactly four validated Short titles are required")
    svc=service()
    items=[(root/"master_final.mp4",story["title"],"long")]+[(root/"shorts"/f"short_{i}.mp4",titles[i-1],f"short_{i}") for i in range(1,5)]
    for path,title,kind in items:
        fp=fingerprint(path); previous=state.get(kind,{})
        if previous.get("fingerprint")==fp and previous.get("video_id"): continue
        video_id=upload(path,title,story["description"],story.get("tags",[]),svc); state[kind]={"fingerprint":fp,"video_id":video_id}
        if kind=="long" and video_id!="SKIPPED_DUPLICATE": set_thumbnail(svc,video_id,root/"thumbnail.jpg")
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(state,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
