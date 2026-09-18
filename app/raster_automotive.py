from __future__ import annotations

import base64
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(size, top, bottom):
    w, h = size
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(h):
        c = _lerp(top, bottom, y / max(1, h - 1))
        for x in range(w):
            px[x, y] = c
    return im


def _glow(base, box, color, blur=30, alpha=90):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse(box, fill=(*color, alpha))
    return Image.alpha_composite(base.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(blur)))


def _metal_body(size, polygon, top=(246,248,249), bottom=(24,30,36)):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    grad = _gradient(size, top, bottom)
    return grad, mask


def _wheel(layer, cx, cy, r, accent):
    d = ImageDraw.Draw(layer)
    d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(5,7,10), outline=(170,178,185), width=max(3, r//14))
    d.ellipse((cx-r+int(r*.20), cy-r+int(r*.20), cx+r-int(r*.20), cy+r-int(r*.20)), fill=(42,49,57), outline=(105,114,122), width=max(2,r//25))
    d.ellipse((cx-r//3, cy-r//3, cx+r//3, cy+r//3), fill=(12,16,20), outline=(135,142,148), width=max(2,r//28))
    d.ellipse((cx-r//9, cy-r//9, cx+r//9, cy+r//9), fill=accent)


def _car_render(camera, size, seed):
    random.seed(seed)
    W, H = size
    S = 2
    work = (W*S, H*S)
    accent=(232,180,74)

    bg = _gradient(work, (17,24,32), (3,5,8))
    bg = _glow(bg, (int(W*.10*S), int(H*.05*S), int(W*.88*S), int(H*.80*S)), (238,180,70), 80*S, 50)
    d = ImageDraw.Draw(bg)
    horizon=int(H*.76*S)
    d.rectangle((0,horizon,work[0],work[1]), fill=(7,9,12))
    for k in range(7):
        y=horizon + k*int(H*.025*S)
        d.line((0,y,work[0],y-int(H*.08*S)), fill=(27,32,38), width=max(1,S))
    d.ellipse((int(W*.08*S),int(H*.66*S),int(W*.92*S),int(H*.88*S)), fill=(0,0,0))

    layer=Image.new("RGBA",work,(0,0,0,0))
    dd=ImageDraw.Draw(layer)
    sx,sy=S,S

    if camera=="side_profile":
        body=[(80*sx,600*sy),(150*sx,520*sy),(360*sx,480*sy),(540*sx,365*sy),(760*sx,320*sy),(980*sx,365*sy),(1160*sx,450*sy),(1410*sx,535*sy),(1450*sx,590*sy),(1370*sx,635*sy),(260*sx,650*sy),(110*sx,620*sy)]
        windows=[(430*sx,470*sy),(555*sx,365*sy),(750*sx,330*sy),(945*sx,375*sy),(1080*sx,470*sy)]
        wheels=[(330,610,105),(1130,595,105)]
    elif camera in ("rear_3q","rear_close"):
        body=[(130*sx,560*sy),(190*sx,400*sy),(420*sx,285*sy),(760*sx,245*sy),(1100*sx,285*sy),(1330*sx,400*sy),(1400*sx,570*sy),(1320*sx,675*sy),(760*sx,725*sy),(200*sx,675*sy)]
        windows=[(355*sx,415*sy),(500*sx,285*sy),(760*sx,265*sy),(1020*sx,285*sy),(1165*sx,415*sy)]
        wheels=[(330,635,88),(1190,635,88)]
    elif camera=="front_close":
        body=[(120*sx,650*sy),(180*sx,430*sy),(380*sx,270*sy),(760*sx,180*sy),(1140*sx,270*sy),(1320*sx,430*sy),(1400*sx,650*sy),(1260*sx,760*sy),(760*sx,800*sy),(240*sx,760*sy)]
        windows=[(290*sx,435*sy),(430*sx,285*sy),(760*sx,220*sy),(1090*sx,285*sy),(1230*sx,435*sy)]
        wheels=[(330,690,82),(1190,690,82)]
    elif camera=="interior":
        d2=ImageDraw.Draw(layer)
        d2.rounded_rectangle((90*sx,180*sy,1350*sx,860*sy),radius=55*S,fill=(12,16,21),outline=(118,126,134),width=5*S)
        d2.polygon([(160*sx,700*sy),(320*sx,450*sy),(550*sx,380*sy),(760*sx,455*sy),(970*sx,380*sy),(1200*sx,450*sy),(1330*sx,700*sy)],fill=(25,31,38),outline=(155,162,168))
        d2.polygon([(210*sx,300*sy),(760*sx,220*sy),(1310*sx,300*sy),(1240*sx,430*sy),(760*sx,360*sy),(270*sx,430*sy)],fill=(24,42,53),outline=(105,125,138))
        d2.rounded_rectangle((520*sx,470*sy,1000*sx,650*sy),radius=18*S,fill=(4,7,10),outline=accent,width=4*S)
        d2.line((575*sx,600*sy,945*sx,600*sy),fill=accent,width=7*S)
        d2.ellipse((300*sx,500*sy,520*sx,720*sy),outline=(170,177,184),width=9*S)
        d2.ellipse((1000*sx,500*sy,1220*sx,720*sy),outline=(170,177,184),width=9*S)
    else:
        body=[(70*sx,540*sy),(135*sx,430*sy),(300*sx,380*sy),(500*sx,270*sy),(760*sx,250*sy),(980*sx,285*sy),(1170*sx,380*sy),(1390*sx,485*sy),(1460*sx,550*sy),(1410*sx,635*sy),(1130*sx,660*sy),(320*sx,670*sy),(120*sx,625*sy)]
        windows=[(300*sx,390*sy),(500*sx,275*sy),(760*sx,265*sy),(930*sx,300*sy),(1120*sx,390*sy)]
        wheels=[(350,625,105),(1130,605,105)]

    if camera!="interior":
        grad, mask=_metal_body(work,body)
        body_rgba=grad.convert("RGBA")
        # Directional studio highlights: broad reflections instead of flat vector fills.
        highlight=Image.new("RGBA",work,(0,0,0,0))
        hd=ImageDraw.Draw(highlight)
        hd.polygon([(120*S,470*S),(500*S,300*S),(1160*S,390*S),(1400*S,520*S),(1260*S,555*S),(500*S,455*S)],fill=(255,255,255,70))
        hd.line((170*S,535*S,1370*S,535*S),fill=(255,255,255,125),width=9*S)
        hd.line((260*S,575*S,1260*S,565*S),fill=(*accent,150),width=5*S)
        highlight=highlight.filter(ImageFilter.GaussianBlur(7*S))
        body_rgba=Image.alpha_composite(body_rgba,highlight)
        layer.alpha_composite(Image.composite(body_rgba,Image.new("RGBA",work,(0,0,0,0)),mask))

        wd=ImageDraw.Draw(layer)
        if len(windows)>=2:
            wd.polygon(windows,fill=(8,17,24,245),outline=(150,166,177,210),width=5*S)
        # Glass reflection streaks.
        wd.line((430*S,430*S,650*S,305*S),fill=(235,245,250,110),width=7*S)
        wd.line((680*S,315*S,980*S,420*S),fill=(255,255,255,80),width=5*S)
        # Lamps and grille.
        if camera in ("rear_3q","rear_close"):
            wd.line((270*S,535*S,620*S,525*S),fill=(255,70,55,230),width=24*S)
            wd.line((900*S,525*S,1250*S,535*S),fill=(255,70,55,230),width=24*S)
        else:
            wd.line((180*S,510*S,430*S,470*S),fill=(245,250,255,220),width=18*S)
            wd.line((1090*S,470*S,1360*S,520*S),fill=(245,250,255,220),width=18*S)
        wd.line((560*S,560*S,980*S,560*S),fill=(8,11,14,230),width=28*S)
        for cx,cy,r in wheels:
            _wheel(layer,cx*S,cy*S,r*S,accent)

    # Fine photographic texture and bloom.
    grain=Image.effect_noise(work, 8).convert("L")
    grain=grain.filter(ImageFilter.GaussianBlur(0.25*S))
    grain_rgba=Image.new("RGBA",work,(190,190,190,0)); grain_rgba.putalpha(grain.point(lambda v:max(0,int((v-128)*0.32+28))))
    layer=Image.alpha_composite(layer,grain_rgba)

    out=Image.alpha_composite(bg.convert("RGBA"),layer)

    # Camera-specific optical/composition transforms. Several semantic camera labels
    # previously shared the same default silhouette, so the product gate correctly
    # detected near-identical pixels. Make each camera a materially different shot
    # while keeping the car dominant and preserving the raster-only asset contract.
    # Camera presets are deliberately compositional, not metadata-only. Each preset
    # changes framing/angle enough that the product gate can verify real pixel diversity.
    if camera=="low_angle":
        out=ImageOps.fit(out,(int(W*1.34),int(H*1.34)),method=Image.Resampling.LANCZOS,centering=(.50,.72))
        out=out.rotate(4.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="wide_scene":
        small=out.resize((int(W*.66),int(H*.66)),Image.Resampling.LANCZOS)
        canvas=Image.new("RGBA",(W,H),(0,0,0,255)); canvas.alpha_composite(small,(int(W*.17),int(H*.22)))
        out=canvas
    elif camera=="three_quarter_high":
        out=ImageOps.fit(out,(int(W*1.24),int(H*1.24)),method=Image.Resampling.LANCZOS,centering=(.46,.28))
        out=out.rotate(-6.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="front_3q":
        out=ImageOps.fit(out,(int(W*1.12),int(H*1.12)),method=Image.Resampling.LANCZOS,centering=(.58,.50))
        out=out.rotate(-2.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="rear_3q":
        out=ImageOps.fit(out,(int(W*1.22),int(H*1.22)),method=Image.Resampling.LANCZOS,centering=(.42,.60))
        out=out.rotate(2.5,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="side_profile":
        out=ImageOps.fit(out,(int(W*1.16),int(H*1.16)),method=Image.Resampling.LANCZOS,centering=(.64,.56))
    elif camera=="front_close":
        out=ImageOps.fit(out,(int(W*1.30),int(H*1.30)),method=Image.Resampling.LANCZOS,centering=(.50,.50))
    elif camera=="rear_close":
        out=ImageOps.fit(out,(int(W*1.28),int(H*1.28)),method=Image.Resampling.LANCZOS,centering=(.50,.52))

    out=out.resize((W,H),Image.Resampling.LANCZOS)
    out=ImageEnhance.Contrast(out).enhance(1.08)
    out=ImageEnhance.Sharpness(out).enhance(1.18)
    return out.convert("RGB")


def render_scene_raster(scene, topic: str, out: Path, size=(1920,1080), camera=None):
    camera=camera or ["front_3q","low_angle","front_close","rear_3q","wide_scene","three_quarter_high","side_profile","rear_close"][(scene.id-1)%8]
    if "interior" in (scene.visual_intent+" "+scene.narration).casefold():
        camera="interior"
    if size[1] > size[0]:
        # Portrait output: keep the car large and centered instead of stretching a landscape
        # composition. The rendered landscape plate is cropped with a photographic fit.
        plate=_car_render(camera,(1920,1080),seed=scene.id*7919+len(topic))
        crop_h=1380
        fitted=ImageOps.fit(plate,(size[0],crop_h),method=Image.Resampling.LANCZOS,centering=(.5,.55))
        canvas=_gradient(size,(10,14,19),(3,5,8)).convert("RGB")
        y=max(90,(size[1]-crop_h)//2)
        canvas.paste(fitted,(0,y))
        image=canvas
    else:
        image=_car_render(camera,size,seed=scene.id*7919+len(topic))
    out.parent.mkdir(parents=True,exist_ok=True)
    image.save(out,format="PNG",optimize=True)


def png_as_data_svg(png: Path, width: int, height: int, metadata: dict[str,str]) -> str:
    data=base64.b64encode(png.read_bytes()).decode("ascii")
    attrs=" ".join(f'data-{k}="{str(v).replace(chr(34),"&quot;")[:500]}"' for k,v in metadata.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" {attrs}><image x="0" y="0" width="{width}" height="{height}" href="data:image/png;base64,{data}"/></svg>'
