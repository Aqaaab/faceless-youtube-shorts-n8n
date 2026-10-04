from __future__ import annotations

import math
from mathutils import Vector


def rig_and_animate(scene_id:int, duration:float, fps:int, mode:str="road") -> dict:
    import bpy
    root=bpy.data.objects.get("ACE_Vehicle_Root") or bpy.data.objects.new("ACE_Vehicle_Root",None)
    if root.name not in bpy.context.scene.objects:
        bpy.context.collection.objects.link(root)
    wheels=[o for o in bpy.data.objects if o.name.startswith("tire_")]
    # A local, dependency-free vehicle rig inspired by production car-rig workflows:
    # root motion, steering, wheel rotation, and subtle suspension pitch/roll.
    root.location=(0,0,0)
    for o in wheels:
        o.parent=root
    end=max(2,int(round(max(0.5,duration)*fps)))
    distance=2.8 if mode in {"road","city","mountain","track","charging"} else 0.0
    direction=-1 if scene_id%2 else 1
    for frame,f in ((1,0.0),(end//2,0.5),(end,1.0)):
        root.location.x=direction*distance*(f-0.5)
        root.rotation_euler.z=direction*math.radians(0.8)*math.sin(math.pi*f)
        root.rotation_euler.y=math.radians(0.7)*math.sin(math.pi*f)
        root.keyframe_insert(data_path="location",frame=frame)
        root.keyframe_insert(data_path="rotation_euler",frame=frame)
        for w in wheels:
            # wheel circumference relation; each wheel is rotated around its local X axis.
            radius=0.64
            w.rotation_euler.x += -direction*(distance*f)/(2*math.pi*radius)
            w.keyframe_insert(data_path="rotation_euler",frame=frame)
    return {"rig":"ACE_Vehicle_Root","wheel_count":len(wheels),"distance":distance,"mode":mode}
