from __future__ import annotations

import base64
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps, ImageChops


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


def _metal_body(size, polygon, top=(205,211,216), bottom=(30,36,42)):
    # Soften the high-resolution silhouette before final downsampling. This rounds
    # polygon joins and prevents the body from reading as vector clip-art.
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    # Larger pre-threshold blur rounds polygon joins into a continuous body contour.
    soft = mask.filter(ImageFilter.GaussianBlur(16))
    mask = soft.point(lambda p: 255 if p >= 96 else 0)

    # Restrained metallic base; the previous bright top made the body read as flat white clip-art.
    grad = _gradient(size, (92,100,108), (18,23,28))
    fields = Image.new("RGBA", size, (0,0,0,0))
    fd = ImageDraw.Draw(fields)
    w,h=size
    fd.ellipse((int(w*.06),int(h*.18),int(w*.62),int(h*.66)), fill=(255,255,255,48))
    fd.ellipse((int(w*.46),int(h*.28),int(w*1.04),int(h*.76)), fill=(210,225,238,34))
    fd.ellipse((int(w*.18),int(h*.54),int(w*.88),int(h*1.02)), fill=(0,0,0,62))
    fields = fields.filter(ImageFilter.GaussianBlur(max(10,int(min(w,h)*.035))))
    shaded = Image.alpha_composite(grad.convert("RGBA"), fields)
    shaded.putalpha(mask)
    return shaded.convert("RGBA"), mask


def _wheel(layer, cx, cy, r, accent):
    """Layered raster wheel with tire sidewall, brake disc, caliper and machined spokes."""
    base=Image.new("RGBA",layer.size,(0,0,0,0)); d=ImageDraw.Draw(base)
    d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(3,5,7,255))
    d.ellipse((cx-r+int(r*.035),cy-r+int(r*.035),cx+r-int(r*.035),cy+r-int(r*.035)),
              fill=(12,15,18,255),outline=(76,82,88,220),width=max(3,r//22))
    side=Image.new("RGBA",layer.size,(0,0,0,0)); sd=ImageDraw.Draw(side)
    sd.arc((cx-r+int(r*.06),cy-r+int(r*.06),cx+r-int(r*.06),cy+r-int(r*.06)),
           205,320,fill=(210,216,220,105),width=max(3,r//28))
    side=side.filter(ImageFilter.GaussianBlur(max(1,r//45))); base=Image.alpha_composite(base,side)
    d=ImageDraw.Draw(base); ir=int(r*.73)
    d.ellipse((cx-ir,cy-ir,cx+ir,cy+ir),fill=(42,47,52,255),outline=(178,184,188,235),width=max(2,r//30))
    d.ellipse((cx-int(r*.60),cy-int(r*.60),cx+int(r*.60),cy+int(r*.60)),
              fill=(17,21,25,255),outline=(92,99,105,230),width=max(2,r//36))
    spokes=Image.new("RGBA",layer.size,(0,0,0,0)); sp=ImageDraw.Draw(spokes)
    for spoke in range(10):
        angle=math.radians(spoke*36)
        x1=cx+int(r*.18*math.cos(angle)); y1=cy+int(r*.18*math.sin(angle))
        x2=cx+int(r*.66*math.cos(angle)); y2=cy+int(r*.66*math.sin(angle))
        sp.line((x1,y1,x2,y2),fill=(206,212,216,220),width=max(3,r//24))
        sp.line((x1+int(r*.025),y1+int(r*.025),x2+int(r*.025),y2+int(r*.025)),
                fill=(54,60,66,190),width=max(2,r//38))
    spokes=spokes.filter(ImageFilter.GaussianBlur(max(1,int(r/180)))); base=Image.alpha_composite(base,spokes)
    d=ImageDraw.Draw(base)
    d.ellipse((cx-int(r*.30),cy-int(r*.30),cx+int(r*.30),cy+int(r*.30)),
              fill=(12,16,20,255),outline=(118,125,131,235),width=max(2,r//30))
    d.rounded_rectangle((cx+int(r*.40),cy-int(r*.32),cx+int(r*.58),cy+int(r*.18)),
                        radius=max(2,r//18),fill=(174,48,42,235))
    d.ellipse((cx-int(r*.10),cy-int(r*.10),cx+int(r*.10),cy+int(r*.10)),
              fill=accent,outline=(235,238,240,230),width=max(2,r//42))
    d.ellipse((cx-int(r*.045),cy-int(r*.045),cx+int(r*.045),cy+int(r*.045)),fill=(218,222,225,255))
    layer.alpha_composite(base)


def _car_render(camera, size, seed, transparent_background=False, portrait_safe=False):
    random.seed(seed)
    W, H = size
    S = 2
    work = (W*S, H*S)
    accent=(232,180,74)

    studio_profiles = {
        "front_close": ((10,22,36),(2,7,14),(108,170,225),58),
        "rear_close": ((28,14,14),(10,3,4),(238,82,62),62),
        "rear_3q": ((17,21,28),(3,5,8),(214,154,78),48),
        "low_angle": ((9,19,29),(2,6,11),(92,150,205),46),
        "three_quarter_high": ((22,20,18),(6,5,4),(236,184,92),50),
        "side_profile": ((14,21,26),(3,6,8),(130,175,205),44),
        "wide_scene": ((11,18,24),(3,6,9),(100,145,185),38),
    }
    top,bottom,glow_color,glow_alpha = studio_profiles.get(camera,((17,24,32),(3,5,8),(238,180,70),50))
    bg = _gradient(work, top, bottom)
    bg = _glow(bg, (int(W*.10*S), int(H*.05*S), int(W*.88*S), int(H*.80*S)), glow_color, 80*S, glow_alpha)
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
    elif camera=="wide_scene":
        body=[(95*sx,555*sy),(180*sx,470*sy),(330*sx,425*sy),(525*sx,330*sy),(760*sx,305*sy),(980*sx,330*sy),(1175*sx,420*sy),(1360*sx,500*sy),(1420*sx,555*sy),(1370*sx,615*sy),(1120*sx,640*sy),(330*sx,650*sy),(140*sx,615*sy)]
        windows=[(330*sx,430*sy),(520*sx,335*sy),(760*sx,315*sy),(940*sx,345*sy),(1110*sx,425*sy)]
        wheels=[(340,615,92),(1120,600,92)]
    else:
        body=[(70*sx,540*sy),(135*sx,430*sy),(300*sx,380*sy),(500*sx,270*sy),(760*sx,250*sy),(980*sx,285*sy),(1170*sx,380*sy),(1390*sx,485*sy),(1460*sx,550*sy),(1410*sx,635*sy),(1130*sx,660*sy),(320*sx,670*sy),(120*sx,625*sy)]
        windows=[(300*sx,390*sy),(500*sx,275*sy),(760*sx,265*sy),(930*sx,300*sy),(1120*sx,390*sy)]
        wheels=[(350,625,105),(1130,605,105)]

    if camera!="interior":
        grad, mask=_metal_body(work,body)
        body_rgba=grad.convert("RGBA")
        # Curved paint-light field: multiple soft specular sources create continuous
        # surface roll-off across the body instead of a flat polygon fill.
        paint_light=Image.new("RGBA",work,(0,0,0,0))
        pl=ImageDraw.Draw(paint_light)
        pl.ellipse((220*S,300*S,1040*S,610*S),fill=(255,255,255,88))
        pl.ellipse((760*S,350*S,1500*S,690*S),fill=(210,225,240,42))
        pl.ellipse((420*S,520*S,1280*S,760*S),fill=(0,0,0,70))
        paint_light=paint_light.filter(ImageFilter.GaussianBlur(72*S))
        body_rgba=Image.alpha_composite(body_rgba,paint_light)
        # Directional studio highlights: broad reflections instead of flat vector fills.
        highlight=Image.new("RGBA",work,(0,0,0,0))
        hd=ImageDraw.Draw(highlight)
        # Broad, low-energy reflections; hard white bands made the car look vector-like.
        hd.polygon([(120*S,470*S),(500*S,300*S),(1160*S,390*S),(1400*S,520*S),(1260*S,555*S),(500*S,455*S)],fill=(255,255,255,24))
        hd.line((190*S,535*S,1360*S,535*S),fill=(245,248,250,58),width=5*S)
        hd.line((280*S,575*S,1250*S,565*S),fill=(*accent,48),width=3*S)
        highlight=highlight.filter(ImageFilter.GaussianBlur(14*S))
        body_rgba=Image.alpha_composite(body_rgba,highlight)
        layer.alpha_composite(Image.composite(body_rgba,Image.new("RGBA",work,(0,0,0,0)),mask))

        wd=ImageDraw.Draw(layer)
        if len(windows)>=2:
            glass_mask=Image.new("L",work,0); ImageDraw.Draw(glass_mask).polygon(windows,fill=255)
            glass_mask=glass_mask.filter(ImageFilter.GaussianBlur(3*S))
            glass_grad=_gradient(work,(24,42,53),(4,9,14)).convert("RGBA")
            glass_high=Image.new("RGBA",work,(0,0,0,0)); ghd=ImageDraw.Draw(glass_high)
            ghd.ellipse((300*S,210*S,1180*S,520*S),fill=(150,190,210,70))
            ghd.line((390*S,455*S,650*S,300*S),fill=(245,250,252,125),width=8*S)
            glass_high=glass_high.filter(ImageFilter.GaussianBlur(7*S))
            glass=Image.alpha_composite(glass_grad,glass_high); glass.putalpha(glass_mask)
            layer=Image.alpha_composite(layer,glass)

        def _light(points,color):
            glow=Image.new("RGBA",work,(0,0,0,0)); gd=ImageDraw.Draw(glow)
            gd.line(points,fill=(*color,95),width=34*S,joint="curve")
            glow=glow.filter(ImageFilter.GaussianBlur(16*S)); layer.alpha_composite(glow)
            mid=Image.new("RGBA",work,(0,0,0,0)); md=ImageDraw.Draw(mid)
            md.line(points,fill=(*color,165),width=13*S,joint="curve")
            mid=mid.filter(ImageFilter.GaussianBlur(4*S)); layer.alpha_composite(mid)
            ImageDraw.Draw(layer).line(points,fill=(*color,245),width=4*S,joint="curve")
        if camera in ("rear_3q","rear_close"):
            _light([(270*S,535*S),(620*S,525*S)],(255,58,48))
            _light([(900*S,525*S),(1250*S,535*S)],(255,58,48))
        else:
            _light([(180*S,510*S),(430*S,470*S)],(232,242,248))
            _light([(1090*S,470*S),(1360*S,520*S)],(232,242,248))

        grille=Image.new("RGBA",work,(0,0,0,0)); gd=ImageDraw.Draw(grille)
        gd.rounded_rectangle((520*S,535*S,1000*S,610*S),radius=24*S,fill=(3,5,7,215),outline=(52,59,66,190),width=3*S)
        for gx in range(555,990,46): gd.line((gx*S,550*S,gx*S,595*S),fill=(92,100,108,80),width=2*S)
        grille=grille.filter(ImageFilter.GaussianBlur(1.1*S)); layer.alpha_composite(grille)

        # Subtle body panel seams and rocker shading add depth without SVG/vector primitives.
        panel=Image.new("RGBA",work,(0,0,0,0))
        pd=ImageDraw.Draw(panel)
        pd.line((390*S,455*S,1110*S,455*S),fill=(235,240,244,38),width=3*S)
        pd.line((410*S,625*S,1080*S,625*S),fill=(0,0,0,58),width=14*S)
        pd.line((520*S,470*S,520*S,615*S),fill=(25,30,35,52),width=3*S)
        pd.line((930*S,465*S,930*S,610*S),fill=(25,30,35,48),width=3*S)
        panel=panel.filter(ImageFilter.GaussianBlur(3*S))
        panel.putalpha(ImageChops.multiply(panel.getchannel("A"),mask))
        layer=Image.alpha_composite(layer,panel)
        wd.line((560*S,560*S,980*S,560*S),fill=(8,11,14,150),width=20*S)
        for cx,cy,r in wheels:
            _wheel(layer,cx*S,cy*S,r*S,accent)

        # Soft wheel-arch occlusion and a floor reflection make the vehicle read as a
        # photographed/rendered object instead of a flat cut-out. Both are raster-only.
        shadow=Image.new("RGBA",work,(0,0,0,0))
        sd=ImageDraw.Draw(shadow)
        sd.ellipse((180*S,610*S,1320*S,760*S),fill=(0,0,0,150))
        shadow=shadow.filter(ImageFilter.GaussianBlur(32*S))
        layer=Image.alpha_composite(shadow,layer)
        reflection=layer.copy().transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        reflection=reflection.crop((0,0,work[0],int(H*.72*S))).resize(work,Image.Resampling.BICUBIC)
        reflection.putalpha(reflection.getchannel("A").point(lambda a:int(a*.11)))
        reflection=reflection.filter(ImageFilter.GaussianBlur(18*S))
        layer=Image.alpha_composite(layer,reflection)

    # Fine photographic texture, soft bloom, and local contrast.
    grain=Image.effect_noise(work, 10).convert("L")
    grain=grain.filter(ImageFilter.GaussianBlur(0.25*S))
    grain_rgba=Image.new("RGBA",work,(190,190,190,0))
    # Keep transparent renders truly transparent outside the vehicle. A full-frame
    # grain alpha previously made alpha_bbox cover the whole 16:9 plate, so portrait
    # fitting scaled the entire plate instead of the actual car silhouette.
    grain_alpha=grain.point(lambda v:max(0,int((v-128)*0.32+28)))
    if transparent_background and camera != "interior":
        grain_alpha=ImageChops.multiply(grain_alpha, mask)
    grain_rgba.putalpha(grain_alpha)
    layer=Image.alpha_composite(layer,grain_rgba)

    out=layer.copy() if transparent_background else Image.alpha_composite(bg.convert("RGBA"),layer)

    # Material-pass: multi-scale pearl/clearcoat texture, masked to the vehicle.
    # This creates actual surface variation in the raster instead of relying on
    # sharp vector-like edges to create the impression of detail.
    if camera != "interior":
        surface_noise=Image.effect_noise(work,46).filter(ImageFilter.GaussianBlur(0.32*S))
        micro=Image.new("RGBA",work,(205,214,222,0))
        micro.putalpha(surface_noise.point(lambda v:max(0,min(92,int(abs(v-128)*1.55)))))
        micro.putalpha(ImageChops.multiply(micro.getchannel("A"),mask.point(lambda p:int(p*0.78))))
        out=Image.alpha_composite(out,micro)

        pearl=Image.effect_noise(work,24).filter(ImageFilter.GaussianBlur(2.8*S))
        pearl_layer=Image.new("RGBA",work,(236,241,245,0))
        pearl_layer.putalpha(pearl.point(lambda v:max(0,min(58,int(abs(v-128)*0.72)))))
        pearl_layer.putalpha(ImageChops.multiply(pearl_layer.getchannel("A"),mask.point(lambda p:int(p*0.62))))
        out=Image.alpha_composite(out,pearl_layer)

        dark_noise=Image.effect_noise(work,22).filter(ImageFilter.GaussianBlur(1.8*S))
        dark=Image.new("RGBA",work,(10,14,18,0))
        dark.putalpha(dark_noise.point(lambda v:max(0,min(74,int(abs(v-128)*0.72)))))
        dark.putalpha(ImageChops.multiply(dark.getchannel("A"),mask.point(lambda p:int(p*0.46))))
        out=Image.alpha_composite(out,dark)

        reflection=Image.new("RGBA",work,(0,0,0,0)); rd=ImageDraw.Draw(reflection)
        rd.arc((80*S,300*S,1420*S,760*S),198,332,fill=(245,250,252,70),width=7*S)
        rd.arc((180*S,270*S,1320*S,700*S),205,320,fill=(210,228,240,48),width=5*S)
        for n in range(6):
            x=int((0.14+n*0.15)*W*S)
            rd.line((x,170*S,x-int(140*S),760*S),fill=(235,242,247,20+n*3),width=max(2,S*3))
        reflection=reflection.filter(ImageFilter.GaussianBlur(11*S))
        reflection.putalpha(ImageChops.multiply(reflection.getchannel("A"),mask.point(lambda p:int(p*0.68))))
        out=Image.alpha_composite(out,reflection)

    def _crop_zoom(image, zoom, center):
        """Apply a true camera crop/zoom; resizing a larger canvas was not a real zoom."""
        zoom=max(1.0,float(zoom))
        IW,IH=image.size
        cw=max(2,int(IW/zoom)); ch=max(2,int(IH/zoom))
        cx=max(cw/2,min(IW-cw/2,float(center[0])*IW))
        cy=max(ch/2,min(IH-ch/2,float(center[1])*IH))
        box=(int(cx-cw/2),int(cy-ch/2),int(cx+cw/2),int(cy+ch/2))
        return image.crop(box).resize((IW,IH),Image.Resampling.LANCZOS)

    # Camera presets are real compositional transforms on the raster image.
    # Portrait-safe mode keeps the complete vehicle readable after recomposition;
    # aggressive landscape crops are intentionally disabled for the 9:16 delivery.
    if camera=="front_3q":
        out=_crop_zoom(out,1.10 if portrait_safe else 1.10,(.47,.52))
        if not transparent_background:
            out=out.rotate(-1.5,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="low_angle":
        out=_crop_zoom(out,1.12 if portrait_safe else 1.82,(.50,.78 if portrait_safe else .82))
        if not transparent_background:
            out=out.rotate(5.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="wide_scene":
        IW,IH=out.size
        small=out.resize((int(IW*.72),int(IH*.72)),Image.Resampling.LANCZOS)
        if transparent_background:
            canvas=Image.new("RGBA",(IW,IH),(0,0,0,0)); canvas.alpha_composite(small,(int(IW*.14),int(IH*.14)))
        else:
            canvas=Image.new("RGBA",(IW,IH),(0,0,0,255)); canvas.alpha_composite(small,(int(IW*.14),int(IH*.14)))
        out=canvas
    elif camera=="three_quarter_high":
        out=_crop_zoom(out,1.16 if portrait_safe else 1.58,(.44,.30 if portrait_safe else .18))
        if not transparent_background:
            out=out.rotate(-9.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(9,13,18,255))
        out=ImageEnhance.Brightness(out).enhance(1.18 if portrait_safe else 1.22)
        hl=Image.new("RGBA",out.size,(0,0,0,0))
        hd=ImageDraw.Draw(hl)
        hd.polygon(
            [(int(out.width*.04),int(out.height*.20)),(int(out.width*.58),int(out.height*.03)),
             (int(out.width*.92),int(out.height*.18)),(int(out.width*.70),int(out.height*.30)),
             (int(out.width*.20),int(out.height*.38))],
            fill=(255,255,255,38),
        )
        out=Image.alpha_composite(out.convert("RGBA"),hl.filter(ImageFilter.GaussianBlur(24)))
    elif camera=="rear_3q":
        out=_crop_zoom(out,1.10 if portrait_safe else 1.28,(.43,.60))
        if not transparent_background:
            out=out.rotate(3.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="side_profile":
        out=_crop_zoom(out,1.08 if portrait_safe else 1.24,(.62,.57))
    elif camera=="front_close":
        # Front close is a deliberately asymmetric lens crop: grille/headlights dominate
        # the foreground instead of mirroring the rear-close composition.
        out=_crop_zoom(out,1.12 if portrait_safe else 1.62,(.40,.48))
        if not transparent_background:
            out=out.rotate(-1.8,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="rear_close":
        # Rear close keeps more lateral body and shifts the taillight band toward frame right.
        out=_crop_zoom(out,1.10 if portrait_safe else 1.26,(.64,.58))
        if not transparent_background:
            out=out.rotate(2.2,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    out=out.resize((W,H),Image.Resampling.LANCZOS)
    out=ImageEnhance.Contrast(out).enhance(1.08)
    out=ImageEnhance.Sharpness(out).enhance(1.18)
    return out.convert("RGBA" if transparent_background else "RGB")


def render_scene_raster(scene, topic: str, out: Path, size=(1920,1080), camera=None):
    camera=camera or ["front_3q","low_angle","front_close","rear_3q","wide_scene","three_quarter_high","side_profile","rear_close"][(scene.id-1)%8]
    # The caller supplies the authoritative camera. Do not infer camera from narration here:
    # doing so can silently render a scene as "interior" while its metadata says "low_angle",
    # which invalidates the pixel-diversity evidence.
    if size[1] > size[0]:
        # Native 9:16 composition: do NOT crop a 16:9 plate into the portrait frame.
        # Render the vehicle on transparency, build a dedicated portrait environment,
        # then recompose the complete car at a readable scale. This eliminates the
        # previous center-crop that reduced Shorts to an unrecognizable body close-up.
        seed=scene.id*7919+len(topic)
        variant=(scene.id-1)%8
        plate=_car_render(camera,(1920,1080),seed=seed,transparent_background=True,portrait_safe=True)
        bg_tops=((10,18,28),(22,18,14),(14,22,29),(10,15,24),(24,20,15),(12,21,31),(18,19,24),(22,17,13))
        bg_bottoms=((3,6,10),(7,5,4),(4,8,11),(3,5,9),(8,6,4),(3,7,11),(5,6,8),(7,5,4))
        image=_gradient(size,bg_tops[variant],bg_bottoms[variant]).convert("RGBA")
        # Studio wall / light field.
        glow=Image.new("RGBA",size,(0,0,0,0))
        gd=ImageDraw.Draw(glow)
        glow_x=(-.35,.05,.18,-.18,.30,-.05,.12,.00)[variant]
        glow_y=(.04,.10,.16,.00,.22,.08,.14,.18)[variant]
        gd.ellipse((int(size[0]*(glow_x)),int(size[1]*glow_y),int(size[0]*(glow_x+1.70)),int(size[1]*(glow_y+.68))),fill=(238,180,70,(42,54,50,46,58,44,52,56)[variant]))
        gd.ellipse((int(size[0]*(.10+.04*variant)),int(size[1]*(.20+.018*variant)),int(size[0]*(.90-.02*variant)),int(size[1]*(.78-.012*variant))),fill=(220,230,238,(24,30,28,22,32,26,30,34)[variant]))
        image=Image.alpha_composite(image,glow.filter(ImageFilter.GaussianBlur(110)))
        # Camera-specific studio lighting is part of the composition, not metadata.
        # Keep it restrained and photographic: each camera gets a different broad
        # ambient field so portrait Shorts remain recognizably related but measurably distinct.
        ambient=Image.new("RGBA",size,(0,0,0,0)); ad=ImageDraw.Draw(ambient)
        ambient_specs=(
            ((125,175,225,48),(-.28,.06,.78,.66)),
            ((245,174,64,56),(.18,.02,1.02,.62)),
            ((175,210,235,46),(-.08,.20,.92,.90)),
            ((105,145,205,50),(.06,-.04,.86,.56)),
            ((235,190,118,58),(-.30,.24,.72,.96)),
            ((130,180,230,48),(.24,.10,1.08,.76)),
            ((190,205,225,44),(-.16,-.02,.66,.80)),
            ((245,174,64,54),(-.02,.30,.98,1.04)),
        )[variant]
        tint,box=ambient_specs
        ad.ellipse((int(size[0]*box[0]),int(size[1]*box[1]),int(size[0]*box[2]),int(size[1]*box[3])),fill=tint)
        image=Image.alpha_composite(image,ambient.filter(ImageFilter.GaussianBlur(98)))
        # Opaque studio floor: keep the full 9:16 delivery frame filled.
        # The previous low-alpha noise mask made the lower band encode as near-black.
        floor=Image.new("RGBA",size,(0,0,0,0)); fd=ImageDraw.Draw(floor); pw,ph=size; fy0=int(ph*.70)
        floor_tints=((25,35,48),(43,34,27),(29,39,47),(24,31,44),(45,38,28),(26,38,51),(34,36,42),(43,33,25))
        fd.rectangle((0,fy0,pw,ph),fill=(*floor_tints[variant],255))
        fd.line((0,fy0,pw,int(ph*.73)),fill=(86,96,108,135),width=max(2,int(ph*.002)))
        for k in range(9):
            x=int(pw*(.04+k*.12)); fd.line((x,int(ph*.74),x-int(pw*.13),ph),fill=(58,66,74,58),width=max(2,int(ph*.0012)))
        # Low-frequency cool studio reflections keep the floor materially non-flat
        # without introducing a bright strip or artificial border.
        for k in range(7):
            yy=int(ph*(.76+k*.035))
            alpha=34+k*5
            fd.line((int(pw*.04),yy,int(pw*.96),yy-int(ph*.012)),fill=(42,70,105,alpha+28),width=max(2,int(ph*.0015)))
        floor_noise=Image.effect_noise(size,22).filter(ImageFilter.GaussianBlur(.45))
        texture=Image.new("RGBA",size,(24,40,64,0))
        texture.putalpha(floor_noise.point(lambda v:int(max(10,min(58,10+abs(v-128)*.40)))))
        floor=Image.alpha_composite(floor,texture)
        image=Image.alpha_composite(image,floor)
        # Crop transparent margins to the actual vehicle silhouette before portrait fitting.
        # Scaling the full 16:9 plate shrank the car into a narrow horizontal band and left
        # too much empty lower frame, weakening both portrait fill and raster texture.
        alpha_bbox=plate.getchannel("A").getbbox()
        if alpha_bbox:
            pad_x=max(24,int(plate.width*.035)); pad_y=max(24,int(plate.height*.035))
            x0=max(0,alpha_bbox[0]-pad_x); y0=max(0,alpha_bbox[1]-pad_y)
            x1=min(plate.width,alpha_bbox[2]+pad_x); y1=min(plate.height,alpha_bbox[3]+pad_y)
            plate=plate.crop((x0,y0,x1,y1))
        camera_portrait = {
            "front_3q": (.84, 0.34, 0.50),
            "low_angle": (.92, 0.39, 0.56),
            "front_close": (1.02, 0.30, 0.50),
            "rear_3q": (.84, 0.36, 0.54),
            "rear_close": (.96, 0.31, 0.51),
            "side_profile": (.78, 0.42, 0.53),
            "three_quarter_high": (.88, 0.29, 0.47),
            "wide_scene": (.70, 0.46, 0.50),
            "interior": (.86, 0.31, 0.50),
        }
        hero_scale, hero_y, hero_x_bias = camera_portrait.get(camera, (.84, .36, .50))
        # Scene-specific camera variation must be visible in the rendered pixels, not only metadata.
        # The prior +/-1.2% scale change left the four Shorts perceptually too similar
        # even though camera IDs differed. Use a restrained 8-shot editorial cadence:
        # wide/hero frames breathe, close frames occupy more of the portrait canvas,
        # while all variants keep the complete vehicle silhouette readable.
        variant_scale=(0.90,0.96,1.04,1.10,0.94,1.07,0.98,1.02)[variant]
        hero_scale *= variant_scale
        hero_w=int(pw*hero_scale); hero_h=max(1,int(plate.height*hero_w/plate.width)); hero=plate.resize((hero_w,hero_h),Image.Resampling.LANCZOS)
        hero=ImageEnhance.Contrast(hero).enhance(1.08+.015*(variant%3)); hero=ImageEnhance.Sharpness(hero).enhance(1.20)
        x_shift=(-34,-18,24,38,-26,30,10,-8)[variant]
        y_shift=(-10,8,18,-16,14,-12,20,-4)[variant]
        hx=int((pw-hero_w)*hero_x_bias + x_shift); hy=int(ph*(hero_y + y_shift/ph))
        # Ground reflection derived from the actual hero alpha, not a black rectangle.
        alpha=hero.getchannel("A")
        refl=hero.transpose(Image.Transpose.FLIP_TOP_BOTTOM); refl.putalpha(alpha.point(lambda a:int(a*.10))); refl=refl.filter(ImageFilter.GaussianBlur(18))
        image.alpha_composite(refl,(hx,int(ph*.70)-refl.height//3))
        image.alpha_composite(hero,(hx,hy))
        # Subtle foreground depth vignette keeps the full frame intentional.
        vignette=Image.new("L",size,0); vd=ImageDraw.Draw(vignette); vd.ellipse((int(-pw*.20),int(-ph*.05),int(pw*1.20),int(ph*1.02)),fill=255); vignette=vignette.filter(ImageFilter.GaussianBlur(95)); dark=Image.new("RGBA",size,(0,0,0,28)); dark.putalpha(ImageChops.invert(vignette)); image=Image.alpha_composite(image,dark)
        image=image.convert("RGB")
    else:
        image=_car_render(camera,size,seed=scene.id*7919+len(topic))
    out.parent.mkdir(parents=True,exist_ok=True)
    image.save(out,format="PNG",optimize=False,compress_level=1)


def png_as_data_svg(png: Path, width: int, height: int, metadata: dict[str,str]) -> str:
    data=base64.b64encode(png.read_bytes()).decode("ascii")
    attrs=" ".join(f'data-{k}="{str(v).replace(chr(34),"&quot;")[:500]}"' for k,v in metadata.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" {attrs}><image x="0" y="0" width="{width}" height="{height}" href="data:image/png;base64,{data}"/></svg>'
