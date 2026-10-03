from __future__ import annotations
import subprocess, tempfile, textwrap
from pathlib import Path
from PIL import Image,ImageEnhance,ImageFilter,ImageFont,ImageDraw
from .arabic_font import discover
from .core import RUN,Story
SIZE=(1280,720)
def generate_thumbnail(story:Story,out:Path=RUN/"thumbnail.jpg")->Path:
    source=RUN/"scenes"/"scene_01.mp4"
    if not source.is_file(): raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="ace-thumb-") as td:
        frame=Path(td)/"frame.jpg"; subprocess.run(["ffmpeg","-v","error","-y","-i",str(source),"-frames:v","1",str(frame)],check=True)
        font_info=discover(); font=ImageFont.truetype(font_info["file"],54)
        with Image.open(frame).convert("RGB") as image:
            image=ImageEnhance.Contrast(image.resize(SIZE)).enhance(1.08); image=image.filter(ImageFilter.UnsharpMask(radius=1.5,percent=120,threshold=3))
            draw=ImageDraw.Draw(image); title=" ".join(str(story.title).split()) or story.topic
            lines=textwrap.wrap(title,width=24,break_long_words=False,break_on_hyphens=False)[:3]; y=64
            for line in lines:
                bbox=draw.textbbox((0,0),line,font=font); x=SIZE[0]-(bbox[2]-bbox[0])-54
                draw.text((x+3,y+3),line,font=font,fill=(0,0,0)); draw.text((x,y),line,font=font,fill=(250,250,250)); y+=68
            out.parent.mkdir(parents=True,exist_ok=True); image.save(out,"JPEG",quality=92,optimize=True)
    return out
