from __future__ import annotations

import math
from mathutils import Vector


def rig_and_animate(scene_id:int, duration:float, fps:int, mode:str="road") -> dict:
    import bpy
    root=bpy.data.objects.get("ACE_Vehicle_Root")
    if root is None:
        root=bpy.data.objects.new("ACE_Vehicle_Root",None)
        bpy.context.collection.objects.link(root)

    # Keep the whole vehicle coherent. World/lighting/camera objects are excluded.
    vehicle_objects=[]
    for o in bpy.context.scene.objects:
        if o.type!="MESH":
            continue
        n=o.name.casefold()
        if any(k in n for k in ("world_","city_","window_band","tunnel_","showroom_","charger","mountain")):
            continue
        if n in {"studio_floor","studio_backdrop"} or n.startswith("display_plinth"):
            continue
        vehicle_objects.append(o)

    for o in vehicle_objects:
        if o is root:
            continue
        o.parent=root

    wheels=[o for o in vehicle_objects if o.name.startswith("tire_")]
    end=max(2,int(round(max(0.5,duration)*fps)))
    distance=2.2 if mode in {"road","city","mountain","track","charging"} else 0.0
    direction=-1 if scene_id%2 else 1
    initial_rotations={w.name:w.rotation_euler.copy() for w in wheels}
    for frame,f in ((1,0.0),(end//2,0.5),(end,1.0)):
        root.location.x=direction*distance*(f-0.5)
        root.rotation_euler.z=direction*math.radians(0.8)*math.sin(math.pi*f)
        root.rotation_euler.y=math.radians(0.7)*math.sin(math.pi*f)
        root.keyframe_insert(data_path="location",frame=frame)
        root.keyframe_insert(data_path="rotation_euler",frame=frame)
        for w in wheels:
            # Circumference-based wheel rotation; preserve any authored orientation.
            base=initial_rotations[w.name].copy()
            base.x += -direction*(distance*f)/(2*math.pi*0.64)
            w.rotation_euler=base
            w.keyframe_insert(data_path="rotation_euler",frame=frame)

    return {"rig":"ACE_Vehicle_Root","wheel_count":len(wheels),"vehicle_meshes":len(vehicle_objects),"distance":distance,"mode":mode}
