import os, json, hashlib
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

SCOPES=["https://www.googleapis.com/auth/youtube.upload","https://www.googleapis.com/auth/youtube.readonly"]

def service():
    c=Credentials(None,refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],token_uri="https://oauth2.googleapis.com/token",client_id=os.environ["YOUTUBE_CLIENT_ID"],client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],scopes=SCOPES)
    c.refresh(Request())
    return build("youtube","v3",credentials=c,cache_discovery=False)

def fingerprint(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def existing_titles(svc, marker):
    ch=svc.channels().list(part="id",mine=True).execute()["items"][0]["id"]
    out=[]; token=None
    while True:
        data=svc.search().list(part="snippet",channelId=ch,forMine=True,type="video",maxResults=50,pageToken=token or "").execute()
        out += [x["snippet"]["title"] for x in data.get("items",[])]
        token=data.get("nextPageToken")
        if not token: break
    return any(marker in t for t in out)

def upload(path,title,description,tags,svc):
    privacy=os.environ.get("YOUTUBE_PRIVACY_STATUS","public").strip().lower()
    if privacy not in {"public","private","unlisted"}: raise ValueError("YOUTUBE_PRIVACY_STATUS must be public, private or unlisted")
    marker=" [ACE:"+fingerprint(path)[:12]+"]"
    final_title=(title[:87]+marker) if len(title)+len(marker)>100 else title+marker
    if existing_titles(svc,marker): return "SKIPPED_DUPLICATE"
    body={"snippet":{"title":final_title,"description":description[:5000],"tags":tags[:500]},"status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":False}}
    req=svc.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(path),mimetype="video/mp4",resumable=True))
    resp=None
    while resp is None: _,resp=req.next_chunk()
    return resp["id"]

def main():
    root=Path("work"); marker=root/"uploaded.json"; state=json.loads(marker.read_text()) if marker.exists() else {}
    story=json.loads((root/"story.json").read_text()); svc=service()
    items=[("master_final.mp4",story["title"],"long")]+[(f"shorts/short_{i}.mp4",f"{story['title']} — Short {i}",f"short_{i}") for i in range(1,5)]
    for rel,title,kind in items:
        p=root/rel; fp=fingerprint(p)
        if state.get(kind,{}).get("fingerprint")==fp: continue
        vid=upload(p,title,story["description"],story.get("tags",[]),svc)
        state[kind]={"fingerprint":fp,"video_id":vid}; marker.write_text(json.dumps(state,indent=2),encoding="utf-8")
    print(json.dumps(state,indent=2))
if __name__=="__main__": main()
