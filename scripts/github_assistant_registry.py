#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'github_assistants.json'
ASSISTANTS=[
 {'name':'yt-dlp','repo':'yt-dlp/yt-dlp','role':'YouTube research metadata/search/media retrieval','integration':'research','license':'Unlicense','enabled_by_default':True},
 {'name':'PySceneDetect','repo':'Breakthrough/PySceneDetect','role':'content-aware scene detection and representative frame sampling','integration':'optional-render-qa','license':'BSD-3-Clause','enabled_by_default':False},
 {'name':'WhisperX','repo':'m-bain/whisperX','role':'word-level transcription/alignment for captions and clip boundaries','integration':'optional-transcript-qa','license':'verify-at-integration-time','enabled_by_default':False},
 {'name':'pyannote-audio','repo':'pyannote/pyannote-audio','role':'speaker diarization and speech activity analysis','integration':'optional-audio-qa','license':'MIT','enabled_by_default':False},
 {'name':'YT-Shorts-Automator','repo':'edyahcks/YT-Shorts-Automator','role':'local Whisper/Ollama/FFmpeg short-selection patterns','integration':'research-reference','license':'verify-at-integration-time','enabled_by_default':False},
 {'name':'clipforge-local','repo':'jayadevrana/clipforge-local','role':'local long-video-to-clip experimentation','integration':'research-reference','license':'verify-at-integration-time','enabled_by_default':False}]
def bootstrap():
 if os.getenv('GITHUB_ACTIONS','').lower()!='true': return
 if os.getenv('ENABLE_FREELLMAPI_PROVIDER','false').lower()!='true' and os.getenv('ENABLE_OLLAMA_PROVIDER','false').lower()!='true': return
 subprocess.run(['bash',str(Path(__file__).resolve().parent/'bootstrap_runtime_free_stack_v2.sh')],check=True,env=os.environ.copy())
 state=RUN_DIR/'ai_router'/'freellmapi.env'
 if state.is_file():
  for line in state.read_text().splitlines():
   if '=' in line:
    k,v=line.split('=',1); os.environ[k]=v
  print('FREE_LOCAL_PROVIDER_ENV=LOADED')
def main():
 bootstrap()
 payload={'schema_version':'1.2','mode':'local_first_optional','assistants':ASSISTANTS,'policy':'External assistants augment internal systems only; they cannot replace Visual QA, Final Feature QA, production contracts, or fail-closed behavior.','local_free_stack':'Ollama + FreeLLMAPI auto-bootstrap in GitHub Actions'}
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print('LOCAL_FREE_STACK_BOOTSTRAP=PASS')
if __name__=='__main__': main()
