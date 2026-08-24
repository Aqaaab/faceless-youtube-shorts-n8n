#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,subprocess,sys,urllib.request
from pathlib import Path
ELEVEN_URL='https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=mp3_44100_128'
CARTESIA_URL='https://api.cartesia.ai/tts/bytes'
def http_post(url,data,headers,timeout=180):
 req=urllib.request.Request(url,data=json.dumps(data).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,r.read()
def clean_cartesia(text):
 text=re.sub(r'\[(?:curious|excited|warm|surprised|playful|serious|pause|slight pause|emphasis|whisper|whispering|laughs|laughing|sighs)\]','',text,flags=re.I)
 return re.sub(r'\s+',' ',text).strip()
def eleven(text,out):
 key=os.getenv('ELEVENLABS_API_KEY','').strip()
 if not key:raise RuntimeError('ELEVENLABS_API_KEY missing')
 voice=os.getenv('ELEVENLABS_VOICE_ID','JBFqnCBsd6RMkjVDRZzb');model=os.getenv('ELEVENLABS_MODEL','eleven_v3')
 if model=='eleven_v3':
  settings={'stability':float(os.getenv('ELEVENLABS_STABILITY','0.35')),'style':float(os.getenv('ELEVENLABS_STYLE','0.20'))}
 else:
  settings={'stability':float(os.getenv('ELEVENLABS_STABILITY','0.30')),'similarity_boost':float(os.getenv('ELEVENLABS_SIMILARITY','0.75')),'style':float(os.getenv('ELEVENLABS_STYLE','0.20')),'use_speaker_boost':True,'speed':float(os.getenv('ELEVENLABS_SPEED','1.0'))}
 status,audio=http_post(ELEVEN_URL.format(voice=voice),{'text':text,'model_id':model,'voice_settings':settings},{'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/mpeg'})
 if status!=200 or not audio:raise RuntimeError(f'ElevenLabs HTTP {status}')
 tmp=str(out)+'.eleven.mp3';Path(tmp).write_bytes(audio)
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',tmp,'-ar','48000','-ac','2','-c:a','pcm_s16le',str(out)],check=True);Path(tmp).unlink(missing_ok=True)
def cartesia(text,out):
 key=os.getenv('CARTESIA_API_KEY','').strip()
 if not key:raise RuntimeError('CARTESIA_API_KEY missing')
 voice=os.getenv('CARTESIA_VOICE_ID','f786b574-daa5-4673-aa0c-cbe3e8534c02');model=os.getenv('CARTESIA_MODEL','sonic-3.5')
 body={'model_id':model,'transcript':clean_cartesia(text),'voice':{'mode':'id','id':voice},'output_format':{'container':'wav','encoding':'pcm_s16le','sample_rate':44100},'language':'en'}
 status,audio=http_post(CARTESIA_URL,body,{'Authorization':f'Bearer {key}','Cartesia-Version':'2026-03-01','Content-Type':'application/json','Accept':'audio/wav'})
 if status!=200 or not audio:raise RuntimeError(f'Cartesia HTTP {status}')
 tmp=str(out)+'.cartesia.wav';Path(tmp).write_bytes(audio)
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',tmp,'-ar','48000','-ac','2','-c:a','pcm_s16le',str(out)],check=True);Path(tmp).unlink(missing_ok=True)
def main():
 if len(sys.argv)<3:raise SystemExit('usage: voice_router.py TEXT_FILE OUTPUT_WAV')
 text=Path(sys.argv[1]).read_text(encoding='utf-8').strip();out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True);errors=[]
 for name,fn in [('ElevenLabs',eleven),('Cartesia',cartesia)]:
  try:
   fn(text,out)
   if out.exists() and out.stat().st_size>1000:print(f'VOICE_PROVIDER={name}');return 0
  except Exception as e:errors.append(f'{name}: {e}');print(f'VOICE_PROVIDER={name} FAILED: {e}',file=sys.stderr)
 print('VOICE_PROVIDER=NONE',file=sys.stderr)
 for e in errors:print(e,file=sys.stderr)
 return 2
if __name__=='__main__':raise SystemExit(main())