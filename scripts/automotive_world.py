from __future__ import annotations

import math
import random
from mathutils import Vector


def _mat(name, color, metallic=0.0, roughness=0.5):
    import bpy
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color=(*color,1.0)
    m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value=(*color,1.0)
        b.inputs["Metallic"].default_value=metallic
        b.inputs["Roughness"].default_value=roughness
    return m


def _cube(name, loc, scale, mat, bevel=0.0):
    import bpy
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o=bpy.context.object; o.name=name; o.scale=scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m=o.modifiers.new("world_bevel","BEVEL"); m.width=bevel; m.segments=2
    o.data.materials.append(mat)
    return o


def build_world(scene_id: int, mode: str = "auto") -> dict:
    import bpy
    random.seed(4100 + int(scene_id))
    mode = (mode or "auto").casefold()
    modes=["road","city","tunnel","showroom","charging","mountain","studio","track"]
    if mode == "auto" or mode not in modes:
        mode=modes[(scene_id-1)%len(modes)]
    floor=_mat("WorldRoad",(0.025,0.030,0.036),0.05,0.42)
    asphalt=_mat("WorldAsphalt",(0.018,0.022,0.026),0.0,0.68)
    concrete=_mat("WorldConcrete",(0.10,0.11,0.12),0.0,0.75)
    glass=_mat("WorldGlass",(0.03,0.08,0.12),0.35,0.18)
    neon=_mat("WorldNeon",(0.03,0.20,0.55),0.15,0.18)
    objs=[]

    # The persistent asset contains a studio floor/backdrop. Hide those only when
    # a real generated environment is selected to avoid z-fighting and duplicated ground.
    for name in ("studio_floor","studio_backdrop","display_plinth"):
        o=bpy.data.objects.get(name)
        if o:
            o.hide_render = mode != "studio"
    if mode in {"road","track","mountain","city","charging"}:
        bpy.ops.mesh.primitive_plane_add(size=100, location=(0,0,0))
        road=bpy.context.object; road.name="world_road"; road.data.materials.append(asphalt); objs.append(road)
        # Lane markers and road shoulders create actual depth cues instead of a flat studio floor.
        for y in (-1.2,1.2):
            _cube("lane_edge",(0,y,0.012),(35,0.035,0.012),concrete,0.01)
        _cube("lane_center",(0,0,0.014),(35,0.018,0.012),neon,0.006)
        for x in range(-30,31,5):
            if (x//5)%2==0:
                _cube("lane_dash",(x,0,0.02),(1.5,0.028,0.012),concrete,0.004)

    if mode in {"city","charging"}:
        for i in range(18):
            x=-28 + i*3.2
            depth=5.0 + random.random()*5.0
            width=1.8 + random.random()*1.8
            height=3.0 + random.random()*10.0
            side=-1 if i%2==0 else 1
            b=_cube("city_building",(x,side*(6+random.random()*4),height/2),(width,2.2,height/2),glass if i%3==0 else concrete,0.08)
            objs.append(b)
            if i%3==0:
                for z in range(2,int(height),2):
                    _cube("window_band",(x,side*(3.75+random.random()*0.1),z),(width*0.55,0.025,0.08),neon,0.01)

    if mode=="tunnel":
        _cube("tunnel_left",(0,-5,3.2),(35,0.25,3.2),concrete,0.08)
        _cube("tunnel_right",(0,5,3.2),(35,0.25,3.2),concrete,0.08)
        _cube("tunnel_roof",(0,0,6.4),(35,5,0.25),concrete,0.08)
        for x in range(-28,29,7):
            _cube("tunnel_light",(x,0,6.05),(1.2,0.22,0.06),neon,0.03)

    if mode=="showroom":
        bpy.ops.mesh.primitive_plane_add(size=55, location=(0,0,0))
        o=bpy.context.object; o.name="showroom_floor"; o.data.materials.append(floor)
        for x in (-10,10):
            _cube("showroom_pillar",(x,4,4),(0.35,0.35,4),concrete,0.08)
        for x in (-14,-7,0,7,14):
            _cube("showroom_strip",(x,0,7),(2.4,0.12,0.08),neon,0.03)

    if mode=="charging":
        _cube("charging_canopy",(5,0,4),(3.2,5,0.2),concrete,0.12)
        for y in (-3.5,3.5):
            _cube("charger",(3,y,1.4),(0.35,0.35,1.4),neon,0.08)

    if mode=="mountain":
        for i in range(16):
            x=-30+i*4
            h=5+random.random()*12
            _cube("mountain",(x,12+h*0.25,h/2),(2.8,5,h/2),concrete,0.2)

    # Remove only objects from this generated layer on subsequent rebuilds.
    for o in objs:
        o["ace_world"]=True
    return {"mode":mode,"objects":len(objs),"world_version":"multi_environment_v1"}


def apply_world_lighting(scene_id: int, mode: str):
    import bpy
    palettes={
        "road":((0.75,0.88,1.0),(1.0,0.35,0.12)),
        "city":((0.35,0.60,1.0),(1.0,0.28,0.08)),
        "tunnel":((0.20,0.55,1.0),(0.95,0.20,0.12)),
        "showroom":((1.0,0.82,0.58),(0.30,0.55,1.0)),
        "charging":((0.25,0.80,1.0),(0.55,0.25,1.0)),
        "mountain":((0.70,0.84,1.0),(1.0,0.58,0.28)),
        "track":((1.0,0.42,0.22),(0.25,0.55,1.0)),
        "studio":((1.0,0.78,0.55),(0.35,0.60,1.0)),
    }
    key,fill=palettes.get(mode,palettes["studio"])
    world=scene.world
    if world and world.use_nodes:
        bg=world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value=(*tuple(c*0.45 for c in key),1)
            bg.inputs["Strength"].default_value=0.22 if mode=="tunnel" else 0.34
    return {"key":key,"fill":fill}
