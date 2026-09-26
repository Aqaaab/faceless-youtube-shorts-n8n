import os
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

CAMERAS = {
    "front_3q": ((7.8, -10.4, 3.15), (0.0, 0.0, 1.02), 56),
    "rear_3q": ((-7.5, 10.0, 3.0), (0.0, 0.0, 1.02), 56),
    "front_close": ((8.2, -7.0, 2.25), (1.55, 0.0, 1.05), 64),
    "rear_close": ((-7.8, 6.8, 2.3), (-1.55, 0.0, 1.02), 64),
    "low_angle": ((8.8, -11.5, 1.35), (0.0, 0.0, 0.92), 58),
    "three_quarter_high": ((8.8, -10.0, 6.1), (0.0, 0.0, 1.0), 58),
    "side_profile": ((0.0, -14.5, 2.55), (0.0, 0.0, 1.12), 58),
    "wide_scene": ((11.8, -16.5, 6.8), (0.0, 0.0, 0.96), 64),
    "interior": ((0.75, -0.62, 1.55), (2.15, 0.0, 1.42), 34),
}

def mat(name, color, metallic=0.0, roughness=0.4, emission=None, transmission=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (*color, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        if "Coat Weight" in b.inputs:
            b.inputs["Coat Weight"].default_value = 0.88
        if "Coat Roughness" in b.inputs:
            b.inputs["Coat Roughness"].default_value = 0.055
        if "IOR" in b.inputs:
            b.inputs["IOR"].default_value = 1.46
        if "Transmission Weight" in b.inputs:
            b.inputs["Transmission Weight"].default_value = transmission
        if emission:
            if "Emission Color" in b.inputs:
                b.inputs["Emission Color"].default_value = (*emission, 1.0)
            if "Emission Strength" in b.inputs:
                b.inputs["Emission Strength"].default_value = 4.0
    return m

def smooth(o):
    if hasattr(o.data, "polygons"):
        for p in o.data.polygons:
            p.use_smooth = True

def bevel(o, width=0.08, segments=4):
    mod = o.modifiers.new("edge_softening", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    return o

def cube(name, loc, scale, material, rotation=(0, 0, 0), bevel_width=0.08):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel_width:
        bevel(o, bevel_width, 5)
    o.data.materials.append(material)
    return o

def cyl(name, loc, radius, depth, material, rotation=(math.pi / 2, 0, 0), bevel_width=0.03):
    bpy.ops.mesh.primitive_cylinder_add(vertices=72, radius=radius, depth=depth, location=loc, rotation=rotation)
    o = bpy.context.object
    o.name = name
    if bevel_width:
        bevel(o, bevel_width, 4)
    smooth(o)
    o.data.materials.append(material)
    return o

def sphere(name, loc, scale, material, segments=72, rings=40):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(o)
    o.data.materials.append(material)
    return o

def torus(name, loc, major, minor, material, rotation=(math.pi / 2, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=96,
        minor_segments=24,
        location=loc,
        rotation=rotation,
    )
    o = bpy.context.object
    o.name = name
    smooth(o)
    o.data.materials.append(material)
    return o

def mesh_object(name, verts, faces, material):
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    smooth(o)
    return o

def loft_body(material):
    xs = [-3.9, -3.65, -3.25, -2.65, -1.8, -0.9, 0.0, 0.95, 1.8, 2.65, 3.25, 3.65, 3.9]
    widths = [0.78, 1.02, 1.30, 1.48, 1.56, 1.60, 1.62, 1.60, 1.55, 1.47, 1.28, 1.00, 0.76]
    zscale = [0.36, 0.46, 0.55, 0.64, 0.70, 0.73, 0.75, 0.74, 0.70, 0.63, 0.54, 0.44, 0.34]
    zc = [0.98, 1.00, 1.02, 1.04, 1.06, 1.08, 1.09, 1.08, 1.06, 1.04, 1.02, 1.00, 0.98]
    ring_n = 20
    verts = []
    for x, w, zs, z0 in zip(xs, widths, zscale, zc):
        for j in range(ring_n):
            a = 2.0 * math.pi * j / ring_n
            y = w * math.cos(a)
            z = z0 + zs * math.sin(a)
            if z < 0.48:
                z = 0.48 + (z - 0.48) * 0.18
            verts.append((x, y, z))
    faces = []
    for i in range(len(xs) - 1):
        for j in range(ring_n):
            nj = (j + 1) % ring_n
            faces.append((i * ring_n + j, (i + 1) * ring_n + j, (i + 1) * ring_n + nj, i * ring_n + nj))
    faces.append(tuple(range(ring_n - 1, -1, -1)))
    off = (len(xs) - 1) * ring_n
    faces.append(tuple(off + j for j in range(ring_n)))
    body = mesh_object("body_shell", verts, faces, material)
    bevel(body, 0.10, 5)
    sub = body.modifiers.new("surface_refinement", "SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1
    return body

def cabin(material, glass):
    shell = sphere("cabin_shell", (-0.15, 0.0, 1.63), (1.72, 1.08, 0.78), material)
    shell.scale.z = 0.84
    # Side glazing panels sit just outside the greenhouse surface.
    left = [
        (1.05, -1.03, 1.58), (0.55, -1.02, 2.19), (-0.72, -0.98, 2.14),
        (-1.40, -1.00, 1.58), (-1.15, -1.04, 1.49), (0.90, -1.04, 1.50)
    ]
    right = [(x, -y, z) for x, y, z in left]
    mesh_object("left_glass", left, [(0, 1, 2, 3, 4, 5)], glass)
    mesh_object("right_glass", right[::-1], [(0, 1, 2, 3, 4, 5)], glass)
    windshield = [
        (0.95, -0.99, 1.53), (0.95, 0.99, 1.53),
        (0.63, 0.82, 2.20), (0.63, -0.82, 2.20)
    ]
    mesh_object("windshield", windshield, [(0, 1, 2, 3)], glass)
    rear = [
        (-1.30, -0.96, 1.54), (-1.30, 0.96, 1.54),
        (-0.76, 0.78, 2.13), (-0.76, -0.78, 2.13)
    ]
    mesh_object("rear_glass", rear, [(0, 1, 2, 3)], glass)
    roof = cube("roof_center", (-0.05, 0.0, 2.24), (0.72, 0.76, 0.055), material, rotation=(0, math.radians(-2), 0), bevel_width=0.05)
    return shell

def wheel(x, side, tire, rim, brake, chrome):
    y = 1.53 * side
    cyl("tire", (x, y, 0.66), 0.60, 0.42, tire)
    torus("tire_sidewall", (x, y - 0.18 * side, 0.66), 0.49, 0.07, tire)
    cyl("brake_disc", (x, y - 0.23 * side, 0.66), 0.43, 0.44, brake)
    cyl("rim", (x, y - 0.26 * side, 0.66), 0.37, 0.46, rim)
    for k in range(10):
        a = math.tau * k / 10.0
        sx = x + math.cos(a) * 0.19
        sz = 0.66 + math.sin(a) * 0.19
        cube("spoke", (sx, y - 0.31 * side, sz), (0.025, 0.025, 0.19), chrome, rotation=(0, a, 0), bevel_width=0.008)
    cyl("hub", (x, y - 0.33 * side, 0.66), 0.095, 0.50, chrome)

def build_car():
    body = mat("CarPaint", (0.018, 0.055, 0.105), 0.94, 0.105)
    body2 = mat("CarPaintAccent", (0.045, 0.12, 0.22), 0.90, 0.135)
    trim = mat("BlackTrim", (0.002, 0.004, 0.006), 0.72, 0.18)
    glass = mat("AutomotiveGlass", (0.008, 0.024, 0.040), 0.12, 0.055, transmission=0.04)
    chrome = mat("Chrome", (0.42, 0.49, 0.57), 0.97, 0.075)
    tire = mat("Tire", (0.0012, 0.0015, 0.0018), 0.0, 0.48)
    rim = mat("MachinedRim", (0.20, 0.24, 0.30), 0.98, 0.08)
    brake = mat("Brake", (0.60, 0.015, 0.012), 0.25, 0.22)
    head = mat("Headlight", (0.70, 0.88, 1.0), 0.10, 0.06, (0.45, 0.72, 1.0))
    tail = mat("Taillight", (1.0, 0.015, 0.008), 0.10, 0.07, (1.0, 0.02, 0.01))
    interior = mat("Interior", (0.025, 0.032, 0.040), 0.30, 0.30)
    screen = mat("Screen", (0.01, 0.035, 0.06), 0.15, 0.08, (0.05, 0.18, 0.35))

    loft_body(body)
    cabin(body, glass)

    for x in (2.35, -2.35):
        for side in (-1, 1):
            torus("fender_arch", (x, side * 1.54, 0.68), 0.72, 0.095, trim)
            wheel(x, side, tire, rim, brake, chrome)

    cube("front_bumper", (3.63, 0, 0.79), (0.26, 1.22, 0.20), body2, bevel_width=0.11)
    cube("rear_bumper", (-3.63, 0, 0.78), (0.24, 1.20, 0.18), body2, bevel_width=0.10)
    cube("front_lip", (3.77, 0, 0.58), (0.12, 1.10, 0.055), chrome, bevel_width=0.02)
    cube("diffuser", (-3.72, 0, 0.55), (0.10, 1.04, 0.065), trim, bevel_width=0.02)

    for side in (-1, 1):
        cube("mirror", (1.02, side * 1.47, 1.60), (0.22, 0.10, 0.085), trim, bevel_width=0.045)
        cube("door_handle", (-0.15, side * 1.53, 1.33), (0.25, 0.025, 0.026), chrome, bevel_width=0.012)
        cube("beltline", (0.0, side * 1.52, 1.39), (2.72, 0.018, 0.018), chrome, bevel_width=0.006)
        cube("lower_character", (0.0, side * 1.48, 1.04), (2.70, 0.012, 0.018), body2, bevel_width=0.006)

    for side in (-1, 1):
        cube("headlamp", (3.53, side * 0.72, 1.17), (0.075, 0.40, 0.12), head, bevel_width=0.045, rotation=(0, side * math.radians(-9), 0))
        cube("tail_lamp", (-3.52, side * 0.77, 1.14), (0.07, 0.41, 0.115), tail, bevel_width=0.04, rotation=(0, side * math.radians(8), 0))
    cube("grille", (3.82, 0, 0.92), (0.045, 0.62, 0.17), trim, bevel_width=0.025)
    for y in (-0.38, -0.13, 0.13, 0.38):
        cube("grille_bar", (3.865, y, 0.92), (0.012, 0.018, 0.15), chrome, bevel_width=0.005)

    # Interior geometry used by the dedicated cabin camera.
    cube("dash", (0.85, 0, 1.58), (0.72, 0.95, 0.10), trim, bevel_width=0.045)
    cube("dash_top", (0.55, 0, 1.73), (1.10, 0.90, 0.035), interior, bevel_width=0.025)
    cube("center_console", (-0.10, 0, 1.37), (0.58, 0.22, 0.07), interior, bevel_width=0.025)
    cube("infotainment", (0.98, 0, 1.83), (0.26, 0.64, 0.055), screen, bevel_width=0.03, rotation=(0, math.radians(-10), 0))
    for side in (-1, 1):
        cube("seat_back", (-0.35, side * 0.51, 1.34), (0.40, 0.26, 0.28), interior, bevel_width=0.10)
        cube("seat_cushion", (-0.05, side * 0.51, 1.12), (0.48, 0.29, 0.11), interior, bevel_width=0.08)
    torus("steering_wheel", (0.72, -0.38, 1.50), 0.24, 0.045, chrome, rotation=(math.pi / 2, 0, 0))
    cube("steering_hub", (0.72, -0.38, 1.50), (0.055, 0.055, 0.055), trim, bevel_width=0.015)

def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

def add_floor():
    floor_mat = mat("StudioFloor", (0.020, 0.026, 0.034), 0.20, 0.19)
    bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "studio_floor"
    floor.data.materials.append(floor_mat)

def area(name, loc, energy, size, color, target=(0, 0, 1.0)):
    d = bpy.data.lights.new(name, "AREA")
    d.energy = energy
    d.shape = "DISK"
    d.size = size
    d.color = color
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.location = loc
    look_at(o, target)
    return o

def setup(width, height, camera_name, scene_id):
    scene = bpy.context.scene
    engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    # Keep CI deterministic while avoiding excessive software-render time on hosted runners.
    if hasattr(scene, "eevee"):
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(scene.eevee, attr):
                try:
                    setattr(scene.eevee, attr, 32)
                except Exception:
                    pass
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.fps = 30
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("AutomotiveWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.0025, 0.005, 0.009, 1)
        bg.inputs["Strength"].default_value = 0.18

    idx = (scene_id - 1) % 8
    lighting = [
        ((1.0, 0.80, 0.58), (0.42, 0.64, 1.0)),
        ((0.50, 0.72, 1.0), (1.0, 0.42, 0.20)),
        ((0.85, 0.92, 1.0), (0.38, 0.58, 1.0)),
        ((1.0, 0.48, 0.34), (0.46, 0.64, 1.0)),
        ((1.0, 0.76, 0.50), (0.35, 0.54, 0.92)),
        ((0.62, 0.82, 1.0), (1.0, 0.60, 0.32)),
        ((0.92, 0.96, 1.0), (0.44, 0.68, 1.0)),
        ((1.0, 0.64, 0.36), (0.50, 0.72, 1.0)),
    ][idx]
    area("key", (4.8, -6.8, 7.4), 1500 + 90 * (scene_id % 3), 5.8, lighting[0])
    area("fill", (-5.8, -3.5, 4.0), 700, 4.8, lighting[1])
    area("rim", (-1.0, 6.0, 5.4), 1350, 3.6, (1.0, 0.24 + 0.04 * idx, 0.13))
    area("top", (0, 0, 9.5), 900, 5.4, (1.0, 1.0, 1.0))
    area("front_soft", (6.8, -10.5, 2.4), 600, 4.4, (0.64, 0.78, 1.0))
    area("floor_soft", (0, -1.5, 0.8), 350, 5.0, (0.30, 0.44, 0.66))

    if camera_name == "interior":
        area("cabin_key", (1.6, -1.8, 2.8), 850, 2.2, (1.0, 0.72, 0.50), (0.6, 0, 1.55))
        area("cabin_fill", (-1.2, 1.5, 2.4), 500, 2.5, (0.42, 0.64, 1.0), (0.6, 0, 1.55))
        area("cabin_top", (0, 0, 3.5), 380, 2.0, (1.0, 1.0, 1.0), (0.6, 0, 1.3))

    data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    pos, target, lens = CAMERAS.get(camera_name, CAMERAS["front_3q"])
    cam.location = Vector(pos)
    cam.data.lens = lens
    cam.data.sensor_width = 36

    # Small deterministic scene offsets make repeated camera slots visibly different.
    phase = ((scene_id * 17) % 9 - 4)
    cam.location += Vector((0.06 * phase, 0.045 * ((scene_id // 8) % 3), 0.025 * ((scene_id % 5) - 2)))
    if height > width:
        cam.data.sensor_fit = "VERTICAL"
        cam.data.lens *= 0.98
        cam.location = Vector(cam.location) * 0.80
        target = (target[0], target[1], target[2] + 0.08)
    look_at(cam, target)

    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.10

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
        output, metadata, width, height, camera, scene_id, topic = a.output, a.metadata, a.width, a.height, a.camera, a.scene_id, a.topic

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_car()
    add_floor()
    setup(width, height, camera, scene_id)
    scene = bpy.context.scene
    scene.render.filepath = str(Path(output).resolve())
    bpy.ops.render.render(write_still=True)
    Path(metadata).write_text(
        json.dumps(
            {
                "renderer": "blender_eevee_automotive_v3",
                "scene_id": scene_id,
                "camera": camera,
                "resolution": [width, height],
                "topic": topic,
                "geometry": "procedural_sculpted_sport_coupe_loft_v3",
                "asset_external": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
