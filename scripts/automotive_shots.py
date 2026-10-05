from __future__ import annotations

import math
from mathutils import Vector

SHOT_PLAN=["hero_front","hero_rear","low_tracking","side_tracking","high_reveal","front_macro","rear_macro","wheel_macro","cockpit","road_follow","orbit_left","orbit_right","top_detail","front_low_wide","rear_low_wide","side_front","side_rear","front_long_lens","rear_long_lens","overhead_reveal","ground_wide","charging_threeq","city_reveal","mountain_reveal","track_follow"]

SHOT_LIBRARY={
 "hero_front":((8.8,-12.0,3.1),(0.4,0,1.0),52),
 "hero_rear":((-8.8,11.5,3.0),(-0.5,0,1.0),52),
 "low_tracking":((11.5,-16.5,0.95),(0.8,0,0.75),48),
 "side_tracking":((0,-13.0,2.1),(0,0,1.0),55),
 "high_reveal":((0.0,-1.0,11.5),(0.0,0.0,0.45),52),
 "front_macro":((7.2,-3.4,1.55),(3.35,-0.62,1.10),68),
 "rear_macro":((-7.0,0.9,2.65),(-4.75,0.05,1.35),72),
 "wheel_macro":((6.0,-7.4,0.62),(2.35,-2.35,0.58),98),
 "cockpit":((0.2,-1.85,1.48),(0.9,-0.02,1.5),43),
 "road_follow":((-7.0,-12.5,2.2),(0.2,0,0.95),52),
 "orbit_left":((10,-10,3.0),(0,0,1.0),55),
 "orbit_right":((10,10,3.0),(0,0,1.0),55),
 "top_detail":((5,-6,7.5),(0.5,0,1.0),58),
 "front_low_wide":((10.8,-15.8,1.05),(1.0,0,0.78),40),
 "rear_low_wide":((-10.8,14.8,1.05),(-0.9,0,0.78),40),
 "side_front":((7.5,-13.5,2.0),(1.0,0,1.05),62),
 "side_rear":((-7.5,-13.5,2.0),(-1.0,0,1.05),62),
 "front_long_lens":((13.5,-18.5,2.7),(1.8,0,1.05),95),
 "rear_long_lens":((-13.5,18.0,2.7),(-1.8,0,1.05),95),
 "overhead_reveal":((3.0,-4.0,10.5),(0.0,0,0.7),48),
 # Ground-level establishing shot: deliberately low, centered and forward-facing so its
 # silhouette/composition cannot collapse into the road-follow chase camera.
 "ground_wide":((-1.8,-20.5,0.28),(1.7,0.0,0.88),30),
 "charging_threeq":((9.8,-12.8,3.4),(0.0,0,1.15),55),
 "city_reveal":((13.0,-16.0,6.5),(0.0,0,0.9),50),
 "mountain_reveal":((11.5,-17.0,5.8),(0.0,0,0.95),52),
 "track_follow":((-11.5,-18.0,1.35),(0.0,0,0.85),46),
}

def choose_shot(scene_id:int, visual_intent:str, mode:str, camera_hint:str="") -> str:
    text=f"{visual_intent} {mode} {camera_hint}".casefold()
    if any(x in text for x in ("interior","cockpit","مقصورة","داخل")): return "cockpit"
    if any(x in text for x in ("wheel","rim","brake","عجلة","جنط","فرامل")): return "wheel_macro"
    return SHOT_PLAN[(scene_id-1) % len(SHOT_PLAN)]


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
      "front_low_wide":(0.13,0.16),"rear_low_wide":(-0.13,0.16),
      "side_front":(0.11,0.07),"side_rear":(-0.11,0.07),
      "front_long_lens":(0.025,-0.025),"rear_long_lens":(-0.025,-0.025),
      "overhead_reveal":(0.10,-0.08),"ground_wide":(0.24,0.16),
      "charging_threeq":(0.09,-0.06),"city_reveal":(0.08,-0.10),
      "mountain_reveal":(-0.08,-0.10),"track_follow":(0.20,0.14),
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
