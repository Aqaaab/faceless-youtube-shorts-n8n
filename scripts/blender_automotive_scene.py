import os
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

CAMERAS = {
    "front_3q": ((8.4,-9.8,3.7),(0,0,1.05),55),
    "rear_3q": ((-8.2,9.4,3.5),(0,0,1.0),55),
    "front_close": ((6.5,-6.8,2.65),(0,0,1.15),62),
    "rear_close": ((-6.3,6.7,2.7),(0,0,1.1),62),
    "low_angle": ((9.2,-11.2,1.65),(0,0,.92),58),
    "three_quarter_high": ((8.7,-9.6,6.4),(0,0,1.0),58),
    "side_profile": ((0,-13.5,2.65),(0,0,1.1),58),
    "wide_scene": ((12.5,-15.5,7.2),(0,0,.95),65),
    "interior": ((.15,-.78,1.55),(0,2.0,1.48),72),
}

def mat(name, color, metallic=0.0, roughness=.4, emission=None):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value=(*color,1)
        b.inputs["Metallic"].default_value=metallic
        b.inputs["Roughness"].default_value=roughness
        if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value=.82
        if "Coat Roughness" in b.inputs: b.inputs["Coat Roughness"].default_value=.08
        if "IOR" in b.inputs: b.inputs["IOR"].default_value=1.46
        if emission:
            if "Emission Color" in b.inputs: b.inputs["Emission Color"].default_value=(*emission,1)
            if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value=5.0
    return m

def cube(name,loc,scale,m,bevel=.12,rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(location=loc,rotation=rotation); o=bpy.context.object
    o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new("bevel","BEVEL"); mod.width=bevel; mod.segments=6
    o.data.materials.append(m); return o

def torus(name,loc,major,minor,m,rotation=(math.pi/2,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=64,minor_segments=16,location=loc,rotation=rotation)
    o=bpy.context.object; o.name=name; bpy.ops.object.shade_smooth(); o.data.materials.append(m); return o

def cyl(name,loc,radius,depth,m):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=radius,depth=depth,location=loc,rotation=(math.pi/2,0,0))
    o=bpy.context.object; o.name=name; o.data.materials.append(m)
    mod=o.modifiers.new("edge","BEVEL"); mod.width=.035; mod.segments=4
    bpy.ops.object.shade_smooth(); return o

def profile_mesh(name, profile, half_width, material, bevel=.12):
    verts=[]
    for y in (-half_width,half_width): verts.extend([(x,y,z) for x,z in profile])
    n=len(profile)
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    for i in range(n):
        j=(i+1)%n; faces.append((i,j,n+j,n+i))
    me=bpy.data.meshes.new(name+"Mesh"); me.from_pydata(verts,[],faces); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(o); o.data.materials.append(material)
    bev=o.modifiers.new("body_edge_softening","BEVEL"); bev.width=bevel; bev.segments=6
    bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.ops.object.shade_smooth(); o.select_set(False)
    return o

def look_at(o,target):
    o.rotation_euler=(Vector(target)-o.location).to_track_quat("-Z","Y").to_euler()

def wheel(x,side,tire,rim,brake,chrome):
    y=1.47*side
    torus("tire",(x,y,.61),.43,.15,tire)
    cyl("rim",(x,y-side*.10,.61),.34,.25,rim)
    cyl("brake",(x,y-side*.14,.61),.21,.28,brake)
    for spoke in range(10):
        a=spoke*math.tau/10; sx=x+math.sin(a)*.22; sz=.61+math.cos(a)*.22
        cube("rim_spoke",(sx,y-side*.17,sz),(.026,.018,.20),chrome,.012,rotation=(0,0,a))

def window_panel(name,loc,scale,rotation,glass):
    return cube(name,loc,scale,glass,.055,rotation=rotation)

def quad_mesh(name, verts, material):
    me=bpy.data.meshes.new(name+"Mesh"); me.from_pydata(verts,[],[(0,1,2,3)]); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(o); o.data.materials.append(material)
    return o

def cabin_prism(name, body):
    # Recognizable coupe/fastback cabin: sloped windshield + rear glass, no floating fins.
    verts=[
        (1.15,-1.25,1.36),(1.15,1.25,1.36),(-1.35,-1.25,1.36),(-1.35,1.25,1.36),
        (.72,-.98,2.20),(.72,.98,2.20),(-.78,-.98,2.12),(-.78,.98,2.12)
    ]
    faces=[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)]
    me=bpy.data.meshes.new(name+"Mesh"); me.from_pydata(verts,[],faces); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(o); o.data.materials.append(body)
    bev=o.modifiers.new("cabin_soft_edges","BEVEL"); bev.width=.08; bev.segments=4
    bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.ops.object.shade_smooth(); o.select_set(False)
    return o

def build_car():
    body=mat("CarPaint",(.025,.075,.14),.93,.16)
    body2=mat("CarPaint2",(.055,.14,.25),.88,.20)
    trim=mat("BlackTrim",(.003,.005,.008),.72,.20)
    glass=mat("Glass",(.008,.035,.055),.12,.08)
    chrome=mat("Chrome",(.42,.48,.56),.96,.10)
    tire=mat("Tire",(.002,.0025,.003),0,.48)
    rim=mat("Rim",(.22,.28,.35),.98,.10)
    brake=mat("Brake",(.72,.018,.012),.25,.22)
    white=mat("Headlight",(.72,.88,1.0),.10,.08,(.45,.65,1.0))
    red=mat("Taillight",(1.0,.015,.006),.08,.09,(1.0,.01,.004))

    # Main body: long, low, rounded sports-coupe proportions.
    cube("lower_body",(0,0,1.02),(3.72,1.42,.48),body,.28)
    cube("shoulder",(0.05,0,1.43),(3.35,1.37,.22),body2,.18)
    cube("hood",(2.18,0,1.52),(1.42,1.34,.18),body,.20,rotation=(0,math.radians(-2),0))
    cube("trunk",(-2.62,0,1.48),(.88,1.30,.20),body,.18,rotation=(0,math.radians(2),0))
    cube("front_bumper",(3.55,0,.88),(.28,1.30,.22),body2,.12)
    cube("rear_bumper",(-3.55,0,.88),(.25,1.28,.20),body2,.10)
    cube("side_sill",(0,0,.62),(3.15,1.45,.10),trim,.06)

    cabin_prism("cabin",body)
    # Glass panels sit directly on the cabin faces.
    quad_mesh("left_side_glass",[(1.00,-1.265,1.48),(-.68,-1.265,1.48),(-.58,-.985,2.06),(.65,-.985,2.14)],glass)
    quad_mesh("right_side_glass",[(1.00,1.265,1.48),(.65,.985,2.14),(-.58,.985,2.06),(-.68,1.265,1.48)],glass)
    quad_mesh("windshield",[(1.01,-1.03,1.53),(1.01,1.03,1.53),(.70,.82,2.14),(.70,-.82,2.14)],glass)
    quad_mesh("rear_glass",[(-.72,-.99,1.50),(-.72,.99,1.50),(-.60,.82,2.06),(-.60,-.82,2.06)],glass)
    cube("roof",(0.02,0,2.16),(.76,.90,.075),body2,.07,rotation=(0,math.radians(-2),0))

    for side in (-1,1):
        cube("a_pillar",(.80,side*1.02,1.80),(.055,.045,.40),trim,.025,rotation=(0,math.radians(-22),0))
        cube("b_pillar",(-.62,side*1.00,1.78),(.055,.045,.35),trim,.022,rotation=(0,math.radians(8),0))
        cube("mirror",(.92,side*1.48,1.55),(.18,.10,.08),trim,.05)
        cube("door_handle",(-.15,side*1.40,1.38),(.28,.025,.025),chrome,.015)
        cube("beltline",(.0,side*1.405,1.46),(2.55,.018,.018),chrome,.008)
        cube("character_line",(.0,side*1.43,1.08),(2.70,.014,.016),body2,.006)

    # Wheels intersect the body naturally; no floating wheel pads.
    for x in (2.28,-2.28):
        for side in (-1,1):
            wheel(x,side,tire,rim,brake,chrome)

    # Lamps, grille and lower aero.
    for side in (-1,1):
        cube("headlamp",(3.52,side*.72,1.25),(.12,.42,.12),white,.055,rotation=(0,side*math.radians(-8),0))
        cube("tail_lamp",(-3.50,side*.76,1.22),(.10,.42,.12),red,.05,rotation=(0,side*math.radians(7),0))
        cube("air_intake",(3.64,side*.90,.78),(.035,.25,.10),trim,.02)
    cube("grille",(3.70,0,.98),(.04,.62,.16),trim,.025)
    cube("grille_bar",(3.745,0,.98),(.012,.48,.015),chrome,.006)
    cube("front_lip",(3.66,0,.64),(.16,1.18,.07),chrome,.035)
    cube("rear_diffuser",(-3.58,0,.65),(.16,1.12,.08),trim,.035)
    cube("roof_spine",(0,0,2.24),(.62,.025,.022),chrome,.008)

    # Interior hints visible through glass.
    cube("dash",(1.02,0,1.58),(.60,.92,.07),trim,.035)
    cube("console",(.15,0,1.36),(.58,.20,.07),trim,.03)
    for side in (-1,1): cube("seat",(-.25,side*.52,1.31),(.44,.30,.16),trim,.08)


def add_floor():
    floor=mat("Floor",(.018,.025,.034),.16,.20); cube("floor",(0,0,-.10),(12,12,.10),floor,.02)
    strip=mat("Reflection",(.13,.17,.23),.34,.12)
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
    if s.world is None: s.world=bpy.data.worlds.new("AutomotiveWorld")
    s.world.use_nodes=True; bg=s.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value=(.004,.008,.014,1); bg.inputs["Strength"].default_value=.22
    area("key",(4,-6,7),1550,5.5,(1.0,.88,.72)); area("fill",(-5,-3,4.5),950,4.5,(.50,.68,1.0))
    area("rim",(-2,5,5.5),1750,4.0,(1.0,.28,.14)); area("top",(0,1,8),1050,4.5,(1,1,1))
    area("front_low",(6,-10,2.0),900,4.0,(.62,.76,1.0)); area("floor_fill",(0,-1,.9),550,5.0,(.38,.50,.68))
    d=bpy.data.cameras.new("Camera"); cam=bpy.data.objects.new("Camera",d); bpy.context.collection.objects.link(cam); s.camera=cam
    pos,target,lens=CAMERAS.get(camera_name,CAMERAS["front_3q"]); cam.location=pos; cam.data.lens=lens; cam.data.sensor_width=36; look_at(cam,target)
    if height>width:
        cam.data.lens*=.83; target_z=1.22 if camera_name!="interior" else 1.45
        cam.rotation_euler=(Vector((0,0,target_z))-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.dof.use_dof=False
    try: s.view_settings.look="AgX - Medium High Contrast"
    except Exception: pass
    s.view_settings.exposure=.20

def main():
    output=os.environ.get("AUTOMOTIVE_RENDER_OUTPUT",""); metadata=os.environ.get("AUTOMOTIVE_RENDER_METADATA","")
    width=int(os.environ.get("AUTOMOTIVE_RENDER_WIDTH","1920")); height=int(os.environ.get("AUTOMOTIVE_RENDER_HEIGHT","1080"))
    camera=os.environ.get("AUTOMOTIVE_RENDER_CAMERA","front_3q"); scene_id=int(os.environ.get("AUTOMOTIVE_RENDER_SCENE_ID","1")); topic=os.environ.get("AUTOMOTIVE_RENDER_TOPIC","")
    if not output or not metadata:
        argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []; p=argparse.ArgumentParser()
        p.add_argument("--output",required=True); p.add_argument("--metadata",required=True); p.add_argument("--width",type=int,required=True); p.add_argument("--height",type=int,required=True); p.add_argument("--camera",required=True); p.add_argument("--scene-id",type=int,required=True); p.add_argument("--topic",default="")
        a=p.parse_args(argv); output,metadata,width,height=a.output,a.metadata,a.width,a.height; camera,scene_id,topic=a.camera,a.scene_id,a.topic
    bpy.ops.wm.read_factory_settings(use_empty=True); build_car(); add_floor(); setup(width,height,camera,scene_id)
    scene=bpy.context.scene; scene.render.filepath=str(Path(output).resolve()); bpy.ops.render.render(write_still=True)
    Path(metadata).write_text(json.dumps({"renderer":"blender_eevee_automotive_v2","scene_id":scene_id,"camera":camera,"resolution":[width,height],"topic":topic,"geometry":"procedural_automotive_3d_curved_profile","asset_external":False},ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__": main()
