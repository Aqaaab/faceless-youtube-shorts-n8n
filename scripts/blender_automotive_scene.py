import os
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
    body=mat("CarPaint",(.055,.095,.16),.92,.13); body2=mat("CarPaint2",(.075,.12,.20),.88,.16)
    trim=mat("BlackTrim",(.006,.009,.013),.55,.20); glass=mat("Glass",(.008,.030,.052),.08,.055)
    chrome=mat("Chrome",(.55,.59,.64),.95,.10); tire=mat("Tire",(.003,.004,.005),0,.64)
    rim=mat("Rim",(.34,.39,.45),.96,.11); brake=mat("Brake",(.72,.025,.018),.30,.24)
    white=mat("Headlight",(.65,.84,1.0),.10,.10,(.55,.78,1.0)); red=mat("Taillight",(1.0,.012,.008),.05,.10,(1.0,.01,.006))
    cube("lower_body",(0,0,.88),(3.72,1.48,.47),body,.42); cube("shoulder",(0.05,0,1.30),(3.38,1.40,.34),body2,.34)
    cube("hood",(2.30,0,1.55),(1.28,1.30,.17),body,.20); cube("trunk",(-2.48,0,1.49),(.78,1.27,.16),body,.18)
    cube("front_bumper",(3.60,0,.75),(.24,1.38,.25),trim,.15); cube("rear_bumper",(-3.60,0,.75),(.24,1.38,.25),trim,.15)
    cube("side_skirt",(0,1.43,.66),(2.72,.10,.15),trim,.08); cube("side_skirt_l",(0,-1.43,.66),(2.72,.10,.15),trim,.08)
    cube("roof",(-.25,0,2.02),(1.88,1.12,.16),body,.18)
    cube("windshield",(1.00,0,1.82),(.88,1.10,.055),glass,.05,rotation=(0,math.radians(-16),0))
    cube("rear_glass",(-1.48,0,1.82),(.68,1.08,.055),glass,.05,rotation=(0,math.radians(14),0))
    for side in (-1,1):
        cube("front_side_window",(.40,side*1.145,1.86),(.72,.035,.34),glass,.045,rotation=(0,math.radians(-5),0))
        cube("rear_side_window",(-1.00,side*1.145,1.86),(.62,.035,.33),glass,.045,rotation=(0,math.radians(8),0))
        cube("a_pillar",(.86,side*1.18,1.86),(.08,.055,.43),trim,.035,rotation=(0,math.radians(-10),0))
        cube("b_pillar",(-.38,side*1.18,1.89),(.07,.055,.40),trim,.03)
        cube("mirror",(1.18,side*1.53,1.70),(.22,.18,.10),trim,.07,rotation=(0,0,side*math.radians(6)))
        cube("door_handle",(-.15,side*1.445,1.34),(.34,.035,.035),chrome,.025)
        cube("beltline",(0,side*1.425,1.47),(2.65,.025,.025),chrome,.012)
        cube("lower_character",(0,side*1.455,.92),(2.80,.018,.018),body2,.008)
    for side in (-1,1):
        cube("headlamp",(3.48,side*.78,1.18),(.13,.50,.17),white,.075,rotation=(0,side*math.radians(-8),0))
        cube("tail_lamp",(-3.48,side*.78,1.16),(.13,.50,.15),red,.065,rotation=(0,side*math.radians(8),0))
        cube("air_intake",(3.73,side*.93,.70),(.045,.30,.12),chrome,.025)
    cube("grille",(3.72,0,.93),(.035,.76,.22),trim,.035); cube("front_lip",(3.66,0,.52),(.18,1.20,.07),chrome,.035)
    cube("rear_diffuser",(-3.66,0,.50),(.18,1.16,.10),trim,.04); cube("center_grille_bar",(3.755,0,.93),(.015,.58,.025),chrome,.01)
    for x in (2.18,-2.18):
        for side in (-1,1):
            wheel(x,side,tire,rim,brake)
            for spoke in range(6):
                ang=spoke*math.tau/6; sx=x+math.sin(ang)*.27; sz=.56+math.cos(ang)*.27
                cube("rim_spoke",(sx,side*1.61,sz),(.045,.025,.27),chrome,.018,rotation=(0,0,ang))
    cube("roof_spine",(-.15,0,2.19),(1.52,.035,.035),chrome,.012); cube("underbody",(0,0,.39),(2.85,1.15,.10),trim,.08)
    cube("dash",(1.00,0,1.63),(.72,1.00,.10),trim,.06); cube("console",(.10,0,1.35),(.72,.25,.10),trim,.045)
    for side in (-1,1): cube("seat",(0.05,side*.52,1.30),(.48,.34,.18),trim,.10)

def add_floor():
    floor=mat("Floor",(.022,.030,.040),.22,.24)
    cube("floor",(0,0,-.10),(12,12,.10),floor,.02)
    strip=mat("Reflection",(.16,.20,.26),.42,.14)
    for x in (-6,-2,2,6): cube("reflection",(x,3.2,.03),(.7,5.5,.015),strip,.01)

def area(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,"AREA"); d.energy=energy; d.shape="DISK"; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); bpy.context.collection.objects.link(o); o.location=loc; look_at(o,(0,0,1)); return o

def setup(width,height,camera_name,scene_id):
    s=bpy.context.scene
    engines=[i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    s.render.engine="BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    s.render.resolution_x=width; s.render.resolution_y=height; s.render.resolution_percentage=100
    s.render.image_settings.file_format="PNG"; s.render.image_settings.color_mode="RGB"; s.render.fps=30
    if s.world is None:
        s.world = bpy.data.worlds.new("AutomotiveWorld")
        s.world.use_nodes = False
    s.world.color=(.006+(scene_id%5)*.001,.010,.016)
    area("key",(3,-6,7),1300,5,(1,.88,.72)); area("fill",(-5,-2,4.5),850,4,(.55,.70,1))
    area("rim",(-1,5,5.5),1500,3.5,(1,.35,.18)); area("top",(0,0,9),1100,4.5,(1,1,1)); area("front_low",(6,-10,2.2),1050,4.0,(.72,.82,1.0)); area("floor_fill",(0,-1,.8),700,5.0,(.42,.55,.72))
    d=bpy.data.cameras.new("Camera"); cam=bpy.data.objects.new("Camera",d); bpy.context.collection.objects.link(cam); s.camera=cam
    pos,target,lens=CAMERAS.get(camera_name,CAMERAS["front_3q"]); cam.location=pos; cam.data.lens=lens; cam.data.sensor_width=36; look_at(cam,target)
    if height>width:
        cam.data.lens*=.76
        target_z = 1.15 if camera_name != "interior" else 1.45
        cam.rotation_euler=(Vector((0,0,target_z))-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.dof.use_dof=False
    try:
        s.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    s.view_settings.exposure = 0.35

def main():
    output = os.environ.get("AUTOMOTIVE_RENDER_OUTPUT", "")
    metadata = os.environ.get("AUTOMOTIVE_RENDER_METADATA", "")
    width = int(os.environ.get("AUTOMOTIVE_RENDER_WIDTH", "1920"))
    height = int(os.environ.get("AUTOMOTIVE_RENDER_HEIGHT", "1080"))
    camera = os.environ.get("AUTOMOTIVE_RENDER_CAMERA", "front_3q")
    scene_id = int(os.environ.get("AUTOMOTIVE_RENDER_SCENE_ID", "1"))
    topic = os.environ.get("AUTOMOTIVE_RENDER_TOPIC", "")
    if not output or not metadata:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        p = argparse.ArgumentParser()
        p.add_argument("--output", required=True)
        p.add_argument("--metadata", required=True)
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--camera", required=True)
        p.add_argument("--scene-id", type=int, required=True)
        p.add_argument("--topic", default="")
        a = p.parse_args(argv)
        output, metadata, width, height = a.output, a.metadata, a.width, a.height
        camera, scene_id, topic = a.camera, a.scene_id, a.topic

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_car()
    add_floor()
    setup(width, height, camera, scene_id)
    scene = bpy.context.scene
    scene.render.filepath = str(Path(output).resolve())
    bpy.ops.render.render(write_still=True)
    Path(metadata).write_text(json.dumps({
        "renderer": "blender_eevee_automotive_v1",
        "scene_id": scene_id,
        "camera": camera,
        "resolution": [width, height],
        "topic": topic,
        "geometry": "procedural_automotive_3d",
        "asset_external": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__=="__main__": main()
