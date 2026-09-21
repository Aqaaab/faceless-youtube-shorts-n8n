import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

CAMERAS = {
    "front_3q": ((7.8,-8.6,4.2),(0,0,1.05),52),
    "rear_3q": ((-7.8,8.6,4.0),(0,0,1.0),52),
    "front_close": ((6.2,-6.0,3.0),(0,0,1.0),58),
    "rear_close": ((-6.0,6.0,3.0),(0,0,1.0),58),
    "low_angle": ((8.8,-10.5,2.0),(0,0,0.85),55),
    "three_quarter_high": ((8.4,-9.2,7.0),(0,0,1.0),58),
    "side_profile": ((0,-12.5,3.0),(0,0,1.0),55),
    "wide_scene": ((11.5,-14.0,7.5),(0,0,0.9),62),
    "interior": ((0.2,-0.8,1.55),(0,2.0,1.45),72),
}

def mat(name, color, metallic=0.0, roughness=0.4, emission=None):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value=(*color,1)
        b.inputs["Metallic"].default_value=metallic
        b.inputs["Roughness"].default_value=roughness
        if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value=0.65
        if "Coat Roughness" in b.inputs: b.inputs["Coat Roughness"].default_value=0.10
        if emission:
            if "Emission Color" in b.inputs: b.inputs["Emission Color"].default_value=(*emission,1)
            if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value=7.0
    return m

def cube(name,loc,scale,m,bevel=0.12,rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(location=loc,rotation=rotation); o=bpy.context.object
    o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new("bevel","BEVEL"); mod.width=bevel; mod.segments=4
    o.data.materials.append(m); return o

def sphere(name,loc,scale,m):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,location=loc); o=bpy.context.object
    o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bpy.ops.object.shade_smooth(); o.data.materials.append(m); return o

def cyl(name,loc,radius,depth,m):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=radius,depth=depth,location=loc,rotation=(math.pi/2,0,0))
    o=bpy.context.object; o.name=name; o.data.materials.append(m)
    mod=o.modifiers.new("edge","BEVEL"); mod.width=.035; mod.segments=3
    bpy.ops.object.shade_smooth(); return o

def look_at(o,target):
    o.rotation_euler=(Vector(target)-o.location).to_track_quat("-Z","Y").to_euler()

def wheel(x,side,tire,rim,brake):
    y=1.42*side
    cyl("tire",(x,y,.56),.56,.34,tire)
    cyl("rim",(x,y-side*.18,.56),.38,.37,rim)
    cyl("brake",(x,y-side*.22,.56),.22,.39,brake)

def build_car():
    body=mat("CarPaint",(.045,.075,.12),.86,.16)
    trim=mat("Trim",(.008,.011,.016),.35,.25)
    glass=mat("Glass",(.012,.045,.070),.05,.08)
    tire=mat("Tire",(.004,.005,.006),0,.72)
    rim=mat("Rim",(.42,.45,.49),.92,.14)
    brake=mat("Brake",(.55,.025,.018),.35,.26)
    white=mat("Headlight",(.70,.88,1.0),0,.12,(.70,.88,1.0))
    red=mat("Taillight",(1.0,.02,.015),0,.12,(1.0,.02,.015))
    cabin=sphere("cabin",(-.15,0,1.96),(2.02,1.20,.70),glass)
    cube("lower_body",(0,0,.94),(3.65,1.48,.52),body,.38)
    cube("upper_body",(.05,0,1.36),(3.25,1.39,.40),body,.46)
    cube("hood",(2.25,0,1.57),(1.25,1.35,.18),body,.22)
    cube("trunk",(-2.35,0,1.55),(.85,1.32,.20),body,.20)
    for x in (-1.75,1.45):
        for y in (-1.16,1.16): cube("pillar",(x,y,1.82),(.14,.10,.55),body,.06)
    for y in (-1.55,1.55): cube("mirror",(1.05,y,1.68),(.20,.16,.11),trim,.06)
    cube("front_bumper",(3.55,0,.78),(.22,1.34,.27),trim,.14)
    cube("rear_bumper",(-3.55,0,.78),(.22,1.34,.27),trim,.14)
    for y in (-.78,.78):
        cube("headlamp",(3.48,y,1.18),(.12,.48,.18),white,.07)
        cube("taillamp",(-3.48,y,1.18),(.12,.48,.16),red,.06)
    cube("grille",(3.70,0,.94),(.04,.72,.18),trim,.04)
    wheel(2.15,-1,tire,rim,brake); wheel(2.15,1,tire,rim,brake)
    wheel(-2.15,-1,tire,rim,brake); wheel(-2.15,1,tire,rim,brake)
    cube("underbody",(0,0,.42),(2.8,1.15,.12),trim,.10)
    cube("dash",(1.0,0,1.72),(.75,1.0,.12),trim,.08)
    cube("console",(.15,0,1.35),(.65,.28,.10),trim,.05)

def add_floor():
    floor=mat("Floor",(.010,.013,.017),.15,.28)
    cube("floor",(0,0,-.10),(12,12,.10),floor,.02)
    strip=mat("Reflection",(0.10,.12,.16),.35,.18)
    for x in (-6,-2,2,6): cube("reflection",(x,3.2,.03),(.7,5.5,.015),strip,.01)

def area(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,"AREA"); d.energy=energy; d.shape="DISK"; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); bpy.context.collection.objects.link(o); o.location=loc; look_at(o,(0,0,1)); return o

def setup(width,height,camera_name,scene_id):
    s=bpy.context.scene
    engines=[i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    s.render.engine="BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    s.render.resolution_x=width; s.render.resolution_y=height; s.render.resolution_percentage=100
    s.render.image_settings.file_format="PNG"; s.render.image_settings.color_mode="RGBA"; s.render.fps=30
    s.world.color=(.006+(scene_id%5)*.001,.010,.016)
    area("key",(3,-6,7),1300,5,(1,.88,.72)); area("fill",(-5,-2,4.5),850,4,(.55,.70,1))
    area("rim",(-1,5,5.5),1500,3.5,(1,.35,.18)); area("top",(0,0,9),900,4.5,(1,1,1))
    d=bpy.data.cameras.new("Camera"); cam=bpy.data.objects.new("Camera",d); bpy.context.collection.objects.link(cam); s.camera=cam
    pos,target,lens=CAMERAS.get(camera_name,CAMERAS["front_3q"]); cam.location=pos; cam.data.lens=lens; cam.data.sensor_width=36; look_at(cam,target)
    if height>width: cam.data.lens*=.88
    cam.data.dof.use_dof=False

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True); p.add_argument("--metadata",required=True)
    p.add_argument("--width",type=int,required=True); p.add_argument("--height",type=int,required=True)
    p.add_argument("--camera",required=True); p.add_argument("--scene-id",type=int,required=True); p.add_argument("--topic",default="")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a=p.parse_args(argv)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_car(); add_floor(); setup(a.width,a.height,a.camera,a.scene_id)
    s=bpy.context.scene; s.render.filepath=str(Path(a.output).resolve()); bpy.ops.render.render(write_still=True)
    Path(a.metadata).write_text(json.dumps({
        "renderer":"blender_eevee_automotive_v1","scene_id":a.scene_id,"camera":a.camera,
        "resolution":[a.width,a.height],"topic":a.topic,"geometry":"procedural_automotive_3d",
        "asset_external":False
    },ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__": main()
