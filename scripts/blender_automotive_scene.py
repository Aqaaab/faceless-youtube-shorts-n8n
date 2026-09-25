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
    # Dedicated cabin camera: a true dashboard/driver perspective, deliberately\n    # orthogonal to the exterior side-profile composition so pixel diversity reflects\n    # genuinely different visual intent rather than two dark, vehicle-dominant frames.\n    "interior": ((1.02,-0.62,1.48),(2.65,0.0,1.34),38),
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
    # Full tire carcass plus a visible sidewall bevel; the previous torus-only tire
    # read as a flat disc at delivery resolution.
    cyl("tire",(x,y,.61),.57,.38,tire)
    torus("tire_sidewall",(x,y-side*.20,.61),.47,.075,tire)
    cyl("rim",(x,y-side*.23,.61),.37,.40,rim)
    cyl("brake",(x,y-side*.27,.61),.235,.43,brake)
    cyl("hub",(x,y-side*.30,.61),.085,.45,chrome)
    for spoke in range(10):
        a=spoke*math.tau/10
        sx=x+math.sin(a)*.255; sz=.61+math.cos(a)*.255
        cube("rim_spoke",(sx,y-side*.32,sz),(.030,.025,.22),chrome,.012,rotation=(0,0,a))

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
    body=mat("CarPaint",(.025,.075,.14),.94,.12)
    body2=mat("CarPaint2",(.050,.125,.22),.90,.15)
    trim=mat("BlackTrim",(.002,.004,.007),.68,.19)
    glass=mat("Glass",(.006,.028,.050),.20,.045)
    chrome=mat("Chrome",(.46,.52,.60),.97,.085)
    tire=mat("Tire",(.0015,.0018,.0022),0,.50)
    rim=mat("Rim",(.22,.27,.34),.98,.09)
    brake=mat("Brake",(.72,.018,.012),.30,.20)
    white=mat("Headlight",(.70,.88,1.0),.10,.07,(.45,.68,1.0))
    red=mat("Taillight",(1.0,.012,.006),.08,.08,(1.0,.008,.004))

    # A continuous profiled shell replaces the stacked rectangular body. The
    # profile is still deterministic, but produces real curvature and readable
    # highlight roll-off at 1920x1080.
    profile_mesh("body_shell",[
        (-3.80,.70),(-3.72,1.02),(-3.45,1.22),(-2.70,1.38),
        (-1.60,1.50),(-.35,1.56),(1.05,1.54),(2.10,1.46),
        (3.00,1.30),(3.55,1.10),(3.78,.74)
    ],1.43,body,.18)

    # Shoulder and lower aero remain separate to create layered specular breaks.
    cube("shoulder",(0.0,0,1.34),(3.22,1.39,.18),body2,.16)
    cube("side_sill",(0,0,.61),(3.12,1.46,.10),trim,.06)
    cube("front_bumper",(3.55,0,.82),(.27,1.28,.20),body2,.13)
    cube("rear_bumper",(-3.55,0,.80),(.25,1.26,.19),body2,.12)
    cube("front_lip",(3.68,0,.57),(.16,1.12,.055),chrome,.028)
    cube("rear_diffuser",(-3.62,0,.55),(.15,1.08,.075),trim,.035)

    cabin_prism("cabin",body)
    # Dark glass panels follow the greenhouse planes rather than sitting on a box roof.
    quad_mesh("left_side_glass",[(1.00,-1.27,1.45),(-.68,-1.27,1.45),(-.58,-.99,2.06),(.65,-.99,2.14)],glass)
    quad_mesh("right_side_glass",[(1.00,1.27,1.45),(.65,.99,2.14),(-.58,.99,2.06),(-.68,1.27,1.45)],glass)
    quad_mesh("windshield",[(1.02,-1.04,1.49),(1.02,1.04,1.49),(.70,.82,2.14),(.70,-.82,2.14)],glass)
    quad_mesh("rear_glass",[(-.74,-1.00,1.48),(-.74,1.00,1.48),(-.60,.82,2.06),(-.60,-.82,2.06)],glass)
    cube("roof",(0.02,0,2.14),(.74,.90,.06),body2,.06,rotation=(0,math.radians(-2),0))

    # Wheel arches and tires are visually separated from the shell.
    for x in (2.28,-2.28):
        for side in (-1,1):
            torus("wheel_arch",(x,side*1.445,.61),.70,.105,trim)
            wheel(x,side,tire,rim,brake,chrome)

    for side in (-1,1):
        cube("a_pillar",(.80,side*1.02,1.80),(.055,.045,.40),trim,.025,rotation=(0,math.radians(-22),0))
        cube("b_pillar",(-.62,side*1.00,1.78),(.055,.045,.35),trim,.022,rotation=(0,math.radians(8),0))
        cube("mirror",(.92,side*1.48,1.55),(.18,.10,.08),trim,.05)
        cube("door_handle",(-.15,side*1.42,1.36),(.28,.025,.025),chrome,.015)
        cube("beltline",(0,side*1.405,1.46),(2.55,.018,.018),chrome,.008)
        cube("character_line",(0,side*1.43,1.05),(2.70,.014,.016),body2,.006)

    for side in (-1,1):
        cube("headlamp",(3.52,side*.72,1.19),(.11,.43,.13),white,.055,rotation=(0,side*math.radians(-8),0))
        cube("tail_lamp",(-3.50,side*.76,1.16),(.10,.44,.12),red,.05,rotation=(0,side*math.radians(7),0))
        cube("air_intake",(3.64,side*.90,.77),(.035,.25,.10),trim,.02)
    cube("grille",(3.70,0,.95),(.04,.62,.17),trim,.025)
    cube("grille_bar",(3.745,0,.95),(.012,.48,.015),chrome,.006)
    cube("roof_spine",(0,0,2.22),(.62,.025,.022),chrome,.008)

    # Minimal interior geometry is visible through the greenhouse and supports the
    # dedicated interior camera without contaminating exterior silhouettes.
    cube("dash",(1.02,0,1.58),(.60,.92,.07),trim,.035)
    cube("console",(.15,0,1.36),(.58,.20,.07),trim,.03)
    for side in (-1,1):
        cube("seat",(-.25,side*.52,1.31),(.44,.30,.16),trim,.08)

def add_floor():
    floor=mat("Floor",(.018,.025,.034),.16,.20); cube("floor",(0,0,-.10),(12,12,.10),floor,.02)

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
        bg.inputs["Color"].default_value=(.003,.006,.011,1); bg.inputs["Strength"].default_value=.20
    area("key",(4.5,-6.5,7.5),1250,5.5,(1.0,.86,.70))
    area("fill",(-5.5,-3.0,4.5),850,4.5,(.48,.66,1.0))
    area("rim",(-1.5,5.5,5.8),1500,3.2,(1.0,.26,.14))
    area("top",(0,0,9.5),1000,5.0,(1,1,1))
    area("front_low",(6.5,-10.0,2.2),850,4.0,(.66,.78,1.0))
    area("floor_fill",(0,-1,.8),500,5.5,(.34,.46,.64))
    if camera_name == "interior":
        # Cabin-specific lighting makes the dedicated interior composition readable at delivery resolution.
        area("cabin_key",(2.0,-1.5,2.8),700,2.2,(1.0,.78,.56))
        area("cabin_fill",(-1.5,1.8,2.3),500,2.0,(.42,.62,1.0))
        area("cabin_top",(0,0,3.6),350,1.8,(1.0,1.0,1.0))
    d=bpy.data.cameras.new("Camera"); cam=bpy.data.objects.new("Camera",d); bpy.context.collection.objects.link(cam); s.camera=cam
    pos,target,lens=CAMERAS.get(camera_name,CAMERAS["front_3q"])
    cam.location=pos; cam.data.lens=lens; cam.data.sensor_width=36; cam.data.dof.use_dof=False
    if height>width:
        # Portrait delivery: tighten the camera and explicitly fit the vertical sensor.
        cam.data.sensor_fit="VERTICAL"
        cam.data.lens*=1.10
        cam.location=Vector(pos)*.86
        target=(target[0],target[1],target[2]+.10)
    look_at(cam,target)
    try: s.view_settings.look="AgX - Medium High Contrast"
    except Exception: pass
    s.view_settings.exposure=.10

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
