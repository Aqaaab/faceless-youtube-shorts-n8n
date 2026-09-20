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
    # Fine wheel hardware keeps the wheel from reading as a flat vector circle.
    for spoke in range(10):
        angle=math.radians(spoke*36)
        x2=cx+int(r*.72*math.cos(angle)); y2=cy+int(r*.72*math.sin(angle))
        d.line((cx,cy,x2,y2),fill=(150,158,166),width=max(2,r//34))
    d.ellipse((cx-r//18,cy-r//18,cx+r//18,cy+r//18),fill=(205,210,214))


def _car_render(camera, size, seed, transparent_background=False, portrait_safe=False):
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

    # Material-pass: low-amplitude surface microvariation and broad studio reflections.
    # This is raster-only and masked to the vehicle so it does not read as a flat
    # polygon with a simple gradient fill.
    if camera != "interior":
        surface_noise=Image.effect_noise(work, 24).filter(ImageFilter.GaussianBlur(0.25*S))
        micro=Image.new("RGBA",work,(205,210,214,0))
        micro.putalpha(surface_noise.point(lambda v:max(0,min(92,int(abs(v-128)*0.72)))))
        micro.putalpha(ImageChops.multiply(micro.getchannel("A"), mask.point(lambda p:int(p*0.42))))
        out=Image.alpha_composite(out,micro)

        reflection=Image.new("RGBA",work,(0,0,0,0))
        rd=ImageDraw.Draw(reflection)
        for n in range(7):
            x=int((0.12+n*0.13)*W*S)
            rd.line((x,160*S,x-int(170*S),760*S),fill=(235,242,247,22+n*3),width=max(2,S*3))
        reflection=reflection.filter(ImageFilter.GaussianBlur(12*S))
        reflection.putalpha(ImageChops.multiply(reflection.getchannel("A"),mask.point(lambda p:int(p*0.55))))
        out=Image.alpha_composite(out,reflection)

    def _crop_zoom(image, zoom, center):
        """Apply a true camera crop/zoom; resizing a larger canvas was not a real zoom."""
        zoom=max(1.0,float(zoom))
        cw=max(2,int(W/zoom)); ch=max(2,int(H/zoom))
        cx=max(cw/2,min(W-cw/2,float(center[0])*W))
        cy=max(ch/2,min(H-ch/2,float(center[1])*H))
        box=(int(cx-cw/2),int(cy-ch/2),int(cx+cw/2),int(cy+ch/2))
        return image.crop(box).resize((W,H),Image.Resampling.LANCZOS)

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
        small=out.resize((int(W*.72),int(H*.72)),Image.Resampling.LANCZOS)
        if transparent_background:
            canvas=Image.new("RGBA",(W,H),(0,0,0,0)); canvas.alpha_composite(small,(int(W*.14),int(H*.14)))
        else:
            canvas=Image.new("RGBA",(W,H),(0,0,0,255)); canvas.alpha_composite(small,(int(W*.14),int(H*.14)))
        out=canvas
    elif camera=="three_quarter_high":
        out=_crop_zoom(out,1.16 if portrait_safe else 1.58,(.44,.30 if portrait_safe else .18))
        if not transparent_background:
            out=out.rotate(-9.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(9,13,18,255))
        out=ImageEnhance.Brightness(out).enhance(1.18 if portrait_safe else 1.22)
        hl=Image.new("RGBA",(W,H),(0,0,0,0))
        hd=ImageDraw.Draw(hl)
        hd.polygon(
            [(int(W*.04),int(H*.20)),(int(W*.58),int(H*.03)),
             (int(W*.92),int(H*.18)),(int(W*.70),int(H*.30)),
             (int(W*.20),int(H*.38))],
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
        out=_crop_zoom(out,1.12 if portrait_safe else 1.48,(.50,.50))
        if not transparent_background:
            out=out.rotate(-1.0,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
    elif camera=="rear_close":
        out=_crop_zoom(out,1.10 if portrait_safe else 1.46,(.50,.52))
        if not transparent_background:
            out=out.rotate(1.5,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(4,6,9,255))
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
        image=_gradient(size,(12,18,25),(3,5,8)).convert("RGBA")
        # Studio wall / light field.
        glow=Image.new("RGBA",size,(0,0,0,0))
        gd=ImageDraw.Draw(glow)
        glow_x=(-.35,.05,.18,-.18,.30,-.05,.12,.00)[variant]
        glow_y=(.04,.10,.16,.00,.22,.08,.14,.18)[variant]
        gd.ellipse((int(size[0]*(glow_x)),int(size[1]*glow_y),int(size[0]*(glow_x+1.70)),int(size[1]*(glow_y+.68))),fill=(238,180,70,52))
        gd.ellipse((int(size[0]*(.10+.04*variant)),int(size[1]*(.20+.018*variant)),int(size[0]*(.90-.02*variant)),int(size[1]*(.78-.012*variant))),fill=(220,230,238,22))
        image=Image.alpha_composite(image,glow.filter(ImageFilter.GaussianBlur(110)))
        # Opaque studio floor: keep the full 9:16 delivery frame filled.
        # The previous low-alpha noise mask made the lower band encode as near-black.
        floor=Image.new("RGBA",size,(0,0,0,0)); fd=ImageDraw.Draw(floor); pw,ph=size; fy0=int(ph*.70)
        fd.rectangle((0,fy0,pw,ph),fill=(14,18,23,255))
        fd.line((0,fy0,pw,int(ph*.73)),fill=(72,80,88,120),width=max(2,int(ph*.002)))
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
        hero_scale=(.76,.94,.82,.90,.96,.79,.92,.85)[variant]
        hero_w=int(pw*hero_scale); hero_h=max(1,int(plate.height*hero_w/plate.width)); hero=plate.resize((hero_w,hero_h),Image.Resampling.LANCZOS)
        hero=ImageEnhance.Contrast(hero).enhance(1.08+.015*(variant%3)); hero=ImageEnhance.Sharpness(hero).enhance(1.16)
        hx=int((pw-hero_w)/2 + (variant-3.5)*18); hy=int(ph*(.34+.018*variant))
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
