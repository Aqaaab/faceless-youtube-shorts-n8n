from __future__ import annotations

import math
from mathutils import Vector

SHOT_LIBRARY={
 "hero_front":((8.8,-12.0,3.1),(0.4,0,1.0),52),
 "hero_rear":((-8.8,11.5,3.0),(-0.5,0,1.0),52),
 "low_tracking":((11.5,-16.5,0.95),(0.8,0,0.75),48),
 "side_tracking":((0,-13.0,2.1),(0,0,1.0),55),
 "high_reveal":((9.5,-10.0,6.8),(0,0,0.9),50),
 "front_macro":((7.2,-3.4,1.55),(3.35,-0.62,1.10),68),
 "rear_macro":((-7.0,0.9,2.65),(-4.75,0.05,1.35),72),
 "wheel_macro":((6.0,-7.4,0.62),(2.35,-2.35,0.58),98),
 "cockpit":((0.2,-1.85,1.48),(0.9,-0.02,1.5),43),
 "road_follow":((-7.0,-12.5,2.2),(0.2,0,0.95),52),
 "orbit_left":((10,-10,3.0),(0,0,1.0),55),
 "orbit_right":((10,10,3.0),(0,0,1.0),55),
 "top_detail":((5,-6,7.5),(0.5,0,1.0),58),
}

def choose_shot(scene_id:int, visual_intent:str, mode:str, camera_hint:str="") -> str:
    text=f"{visual_intent} {mode} {camera_hint}".casefold()
    if any(x in text for x in ("interior","cockpit","مقصورة","داخل")): return "cockpit"
    if any(x in text for x in ("wheel","rim","brake","عجلة","جنط","فرامل")): return "wheel_macro"
    if any(x in text for x in ("detail","grille","lamp","مصباح","تفاصيل")): return "front_macro" if scene_id%2 else "rear_macro"
    if any(x in text for x in ("performance","speed","track","أداء","سرعة")): return "low_tracking" if scene_id%2 else "road_follow"
    if any(x in text for x in ("technology","charging","تقنية","شحن")): return "high_reveal" if scene_id%2 else "side_tracking"
    if mode=="tunnel": return "side_tracking" if scene_id%2 else "road_follow"
    if mode in {"city","mountain"}: return "high_reveal" if scene_id%2 else "hero_front"
    sequence=["hero_front","side_tracking","low_tracking","rear_macro","high_reveal","cockpit","wheel_macro","hero_rear","road_follow","orbit_left","orbit_right","top_detail"]
    return sequence[(scene_id-1)%len(sequence)]

def create_camera(scene, name, shot, width, height, scene_id):
    import bpy
    pos,target,lens=SHOT_LIBRARY.get(shot,SHOT_LIBRARY["hero_front"])
    if height>width:
        target=Vector(target); p=Vector(pos)
        p=target+(p-target)*0.70
        lens=max(44,lens-5)
        pos=tuple(p)
    data=bpy.data.cameras.new(f"Camera_{name}")
    cam=bpy.data.objects.new(f"Camera_{name}",data)
    bpy.context.collection.objects.link(cam)
    cam.location=Vector(pos)
    data.lens=lens
    data.sensor_width=36
    data.sensor_fit="VERTICAL" if height>width else "HORIZONTAL"
    direction=Vector(target)-cam.location
    cam.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    data.clip_start=0.03; data.clip_end=250
    if shot in {"front_macro","rear_macro","wheel_macro","cockpit"}:
        data.dof.use_dof=True
        data.dof.focus_distance=max(0.5,direction.length*0.82)
        data.dof.aperture_fstop=3.2 if shot=="wheel_macro" else 4.0
    return cam

def animate_camera(cam, shot, scene_id, duration, fps):
    import bpy
    end=max(2,int(round(max(0.5,duration)*fps)))
    start=cam.location.copy()
    _, authored_target, _ = SHOT_LIBRARY.get(shot,SHOT_LIBRARY["hero_front"])
    target=Vector(authored_target)
    radius=max(1.0,(start-target).length)
    theta=math.atan2(start.y-target.y,start.x-target.x)
    motions={
      "hero_front":(0.08,0.08),"hero_rear":(-0.07,0.07),
      "low_tracking":(0.14,0.13),"side_tracking":(0.18,0.06),
      "high_reveal":(0.10,-0.12),"front_macro":(0.06,-0.08),
      "rear_macro":(-0.035,-0.045),"wheel_macro":(0.20,0.045),
      "cockpit":(0.035,-0.03),"road_follow":(0.16,0.10),
      "orbit_left":(0.22,0.10),"orbit_right":(-0.22,0.10),"top_detail":(0.12,-0.10)
    }
    orbit,dolly=motions.get(shot,(0.10,0.08))
    for frame,f in ((1,0.0),(end//2,0.5),(end,1.0)):
        if f == 0.0:
            cam.location=Vector(start)
            direction=target-cam.location
        else:
            angle=theta+orbit*(f-0.5)
            scale=1.0-dolly*(f-0.5)
            cam.location=target+Vector((math.cos(angle)*radius*scale,math.sin(angle)*radius*scale,start.z-target.z+0.10*math.sin(math.pi*f)))
            direction=target+Vector((0,0,0.04*math.sin(math.pi*f)))-cam.location
        cam.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
        cam.keyframe_insert(data_path="location",frame=frame)
        cam.keyframe_insert(data_path="rotation_euler",frame=frame)
    return end
