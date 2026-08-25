#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
ASSISTANTS=[
 {'name':'TubeTranscript','repo':'apexpdl/youtube-transcribe','role':'transcript retrieval with Whisper fallback','integration':'optional-transcript-research'},
 {'name':'YT-Shorts-Automator','repo':'edyahcks/YT-Shorts-Automator','role':'local Whisper/Ollama/FFmpeg clip-selection reference','integration':'clip-selection-patterns'},
 {'name':'OmniTranscripts','repo':'wilmoore/OmniTranscripts','role':'production-oriented multi-source transcription','integration':'optional-transcript-service'},
 {'name':'mcp-video-analyzer','repo':'guimatheus92/mcp-video-analyzer','role':'video metadata, transcripts, key frames and OCR','integration':'optional-multimodal-research'},
]
OUT=RUN_DIR/'github_assistants.json'
def main():
 p={'schema_version':'1.0','mode':'local_first_optional','assistants':ASSISTANTS,'policy':'External assistants must augment, never replace, internal QA or deterministic production contracts.'}
 OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(p,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
