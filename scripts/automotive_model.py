from __future__ import annotations

import math
import subprocess as _subprocess
from pathlib import Path

import bpy
from mathutils import Vector


def _node(material, name="Principled BSDF"):
    if not material.use_nodes:
        material.use_nodes = True
    return material.node_tree.nodes.get(name)


def material(name, color, metallic=0.0, roughness=0.4, transmission=0.0, emission=None, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.use_nodes = True
    b = _node(m)
    if b is None:
        return m
    for key, value in (
        ("Base Color", (*color, 1.0)),
        ("Metallic", metallic),
        ("Roughness", roughness),
        ("Transmission Weight", transmission),
        ("Coat Weight", coat),
        ("Coat Roughness", 0.045),
    ):
        if key in b.inputs:
            b.inputs[key].default_value = value
    if "IOR" in b.inputs:
        b.inputs["IOR"].default_value = 1.46
    if emission:
        if "Emission Color" in b.inputs:
            b.inputs["Emission Color"].default_value = (*emission, 1.0)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = 2.8

    # Physically plausible micro-surface variation prevents close/portrait
    # automotive shots from becoming unnaturally smooth CGI plates. This is
    # shader-level detail, not a gate relaxation or post-render noise overlay.
    if name in {"CarPaint", "CarPaintAccent", "InteriorLeather", "Tire"}:
        nodes = m.node_tree.nodes
        links = m.node_tree.links
        noise = nodes.get("micro_surface_noise") or nodes.new("ShaderNodeTexNoise")
        noise.name = "micro_surface_noise"
        bump = nodes.get("micro_surface_bump") or nodes.new("ShaderNodeBump")
        bump.name = "micro_surface_bump"
        noise.inputs["Scale"].default_value = {
            "CarPaint": 28.0,
            "CarPaintAccent": 30.0,
            "InteriorLeather": 42.0,
            "Tire": 24.0,
        }[name]
        noise.inputs["Detail"].default_value = 5.0
        noise.inputs["Roughness"].default_value = 0.68
        bump.inputs["Strength"].default_value = {
            "CarPaint": 0.075,
            "CarPaintAccent": 0.085,
            "InteriorLeather": 0.12,
            "Tire": 0.10,
        }[name]
        bump.inputs["Distance"].default_value = 0.028
        for link in list(links):
            if link.to_node == bump and link.to_socket == bump.inputs["Height"]:
                links.remove(link)
            if link.to_node == b and link.to_socket == b.inputs["Normal"]:
                links.remove(link)
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def smooth(obj):
    if hasattr(obj.data, "polygons"):
        for p in obj.data.polygons:
            p.use_smooth = True


def bevel(obj, width=0.08, segments=3):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(25)
    return obj


def cube(name, loc, scale, mat, rotation=(0.0, 0.0, 0.0), bevel_width=0.05):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel_width:
        bevel(obj, bevel_width, 4)
    obj.data.materials.append(mat)
    return obj


def cylinder(name, loc, radius, depth, mat, rotation=(math.pi / 2, 0.0, 0.0), vertices=64, bevel_width=0.025):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    if bevel_width:
        bevel(obj, bevel_width, 3)
    smooth(obj)
    obj.data.materials.append(mat)
    return obj


def torus(name, loc, major, minor, mat, rotation=(math.pi / 2, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=96,
        minor_segments=20,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    smooth(obj)
    obj.data.materials.append(mat)
    return obj


def sphere(name, loc, scale, mat, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(obj)
    obj.data.materials.append(mat)
    return obj


def mesh_object(name, verts, faces, mat, smooth_mesh=True):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if smooth_mesh:
        smooth(obj)
    return obj


def loft_body(mat):
    # A low-poly automotive shell with flattened lower sections, broad shoulders,
    # tapered nose/tail and enough longitudinal sections to carry real highlights.
    sections = [
        (-4.05, 0.72, 0.38, 0.92),
        (-3.82, 0.98, 0.48, 0.95),
        (-3.35, 1.28, 0.61, 0.99),
        (-2.70, 1.48, 0.72, 1.03),
        (-1.85, 1.58, 0.78, 1.06),
        (-0.85, 1.64, 0.82, 1.08),
        (0.10, 1.65, 0.84, 1.09),
        (1.00, 1.61, 0.81, 1.08),
        (1.85, 1.54, 0.73, 1.05),
        (2.65, 1.43, 0.65, 1.02),
        (3.32, 1.25, 0.56, 0.98),
        (3.78, 0.96, 0.46, 0.95),
        (4.02, 0.68, 0.34, 0.92),
    ]
    ring_n = 28
    verts = []
    for x, width, height, z0 in sections:
        for j in range(ring_n):
            a = math.tau * j / ring_n
            # Superellipse-like cross-section: flatter floor and shoulder, round roof.
            c = math.cos(a)
            s = math.sin(a)
            y = width * (1.0 if abs(c) < 0.3 else 0.94) * c
            z = z0 + height * s
            if z < 0.50:
                z = 0.50 + (z - 0.50) * 0.12
            if s > 0.35:
                z += 0.035 * (1.0 - abs(c))
            verts.append((x, y, z))
    faces = []
    for i in range(len(sections) - 1):
        for j in range(ring_n):
            nj = (j + 1) % ring_n
            faces.append((i * ring_n + j, (i + 1) * ring_n + j,
                          (i + 1) * ring_n + nj, i * ring_n + nj))
    faces.append(tuple(range(ring_n - 1, -1, -1)))
    off = (len(sections) - 1) * ring_n
    faces.append(tuple(off + j for j in range(ring_n)))
    body = mesh_object("body_shell", verts, faces, mat)
    bevel(body, 0.075, 3)
    return body


def cut_wheel_wells(body):
    cutters = []
    for x, tag in ((2.35, "f"), (-2.35, "r")):
        cutter = cylinder(
            f"_well_cutter_{tag}",
            (x, 0.0, 0.68),
            0.76,
            4.2,
            bpy.data.materials.get("BlackTrim"),
            vertices=64,
            bevel_width=0.0,
        )
        cutters.append(cutter)
        mod = body.modifiers.new(f"wheel_well_{tag}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        # Keep the Boolean in the authored modifier stack. Applying a later modifier out
        # of stack order changes the evaluated geometry and produced CI warnings.
        # Keep the cutter alive because the Boolean modifier evaluates its object reference
        # during render. Deleting it here leaves a dangling modifier and can silently remove
        # the intended wheel-well cutout on some Blender builds.
        cutter.hide_render = True
        cutter.hide_viewport = True


def greenhouse(glass, trim, roof_mat):
    # Explicit greenhouse volume: front and rear pillars, side glazing, roof.
    verts = [
        (1.28, -0.98, 1.40), (1.28, 0.98, 1.40),
        (0.58, -0.83, 2.20), (0.58, 0.83, 2.20),
        (-1.28, -0.86, 2.12), (-1.28, 0.86, 2.12),
        (-1.62, -0.98, 1.40), (-1.62, 0.98, 1.40),
    ]
    faces = [
        (0, 1, 3, 2), (2, 3, 5, 4), (4, 5, 7, 6),
        (0, 2, 4, 6), (1, 7, 5, 3),
    ]
    shell = mesh_object("greenhouse_shell", verts, faces, trim, smooth_mesh=False)
    # Side glass panels are separate surfaces, making the glass-to-body relationship legible.
    mesh_object("left_side_glass", [verts[i] for i in (0, 2, 4, 6)], [(0, 1, 2, 3)], glass, False)
    mesh_object("right_side_glass", [verts[i] for i in (1, 3, 5, 7)], [(0, 1, 2, 3)], glass, False)
    mesh_object("windshield_glass", [verts[i] for i in (0, 1, 3, 2)], [(0, 1, 2, 3)], glass, False)
    mesh_object("rear_glass", [verts[i] for i in (4, 5, 7, 6)], [(0, 1, 2, 3)], glass, False)
    cube("roof_panel", (-0.45, 0.0, 2.18), (1.15, 0.84, 0.055), roof_mat, bevel_width=0.045)
    # Pillars create a realistic segmented greenhouse instead of a single blob.
    for side in (-1, 1):
        cube("a_pillar_" + str(side), (0.91, side * 0.91, 1.80), (0.075, 0.055, 0.44), trim, rotation=(0.0, side * math.radians(-24), 0.0), bevel_width=0.018)
        cube("b_pillar_" + str(side), (-0.58, side * 0.90, 1.76), (0.065, 0.055, 0.38), trim, rotation=(0.0, side * math.radians(7), 0.0), bevel_width=0.018)
    return shell


def wheel(x, side, mats, tag):
    y = 1.57 * side
    tire, rim, brake, chrome = mats
    cylinder(f"tire_{tag}", (x, y, 0.68), 0.64, 0.40, tire)
    torus(f"tire_sidewall_{tag}", (x, y - 0.205 * side, 0.68), 0.52, 0.065, tire)
    cylinder(f"brake_{tag}", (x, y - 0.235 * side, 0.68), 0.45, 0.28, brake)
    torus(f"rim_{tag}", (x, y - 0.30 * side, 0.68), 0.40, 0.055, rim)
    for k in range(10):
        a = math.tau * k / 10.0
        sx = x + math.cos(a) * 0.28
        sz = 0.68 + math.sin(a) * 0.28
        cube(
            f"spoke_{tag}_{k}",
            (sx, y - 0.325 * side, sz),
            (0.032, 0.024, 0.255),
            chrome,
            rotation=(0.0, a, 0.0),
            bevel_width=0.012,
        )
    cylinder(f"hub_{tag}", (x, y - 0.34 * side, 0.68), 0.105, 0.20, chrome)


def fender_arch(x, side, trim, tag):
    y = 1.585 * side
    torus(f"wheel_{tag}_arch", (x, y, 0.68), 0.76, 0.075, trim)


def light_cluster(mats):
    body2, trim, chrome, head, tail = mats
    for side in (-1, 1):
        cube(
            f"headlamp_{'l' if side < 0 else 'r'}",
            (3.63, side * 0.70, 1.18),
            (0.08, 0.36, 0.14),
            head,
            rotation=(0.0, side * math.radians(-8), 0.0),
            bevel_width=0.05,
        )
        cube(
            f"tail_lamp_{'l' if side < 0 else 'r'}",
            (-3.63, side * 0.75, 1.15),
            (0.075, 0.38, 0.13),
            tail,
            rotation=(0.0, side * math.radians(8), 0.0),
            bevel_width=0.045,
        )
    cube("front_bumper", (3.75, 0.0, 0.82), (0.28, 1.25, 0.23), body2, bevel_width=0.12)
    cube("rear_bumper", (-3.75, 0.0, 0.80), (0.25, 1.22, 0.21), body2, bevel_width=0.11)
    cube("front_lip", (3.93, 0.0, 0.58), (0.12, 1.10, 0.06), chrome, bevel_width=0.02)
    cube("rear_diffuser", (-3.88, 0.0, 0.56), (0.11, 1.05, 0.065), trim, bevel_width=0.02)
    cube("front_grille", (3.92, 0.0, 0.95), (0.05, 0.68, 0.18), trim, bevel_width=0.03)
    for y in (-0.45, -0.15, 0.15, 0.45):
        cube("grille_bar", (3.98, y, 0.95), (0.014, 0.018, 0.145), chrome, bevel_width=0.005)


def exterior_detail(body2, trim, chrome):
    for side in (-1, 1):
        cube(f"mirror_{side}", (1.05, side * 1.52, 1.62), (0.20, 0.11, 0.085), trim, bevel_width=0.045)
        cube(f"door_handle_{side}", (-0.20, side * 1.58, 1.36), (0.24, 0.026, 0.026), chrome, bevel_width=0.012)
        cube(f"beltline_{side}", (0.0, side * 1.57, 1.42), (2.70, 0.016, 0.020), chrome, bevel_width=0.007)
        cube(f"side_skirt_{side}", (0.0, side * 1.54, 0.75), (2.80, 0.035, 0.10), trim, bevel_width=0.025)
        cube(f"character_line_{side}", (0.0, side * 1.50, 1.08), (2.62, 0.014, 0.018), body2, bevel_width=0.006)
    # Hood and rear-deck crease cues.
    for y in (-0.72, 0.72):
        cube("hood_crease", (2.05, y, 1.30), (1.00, 0.018, 0.018), chrome, bevel_width=0.006)
        cube("rear_crease", (-2.15, y, 1.24), (0.85, 0.014, 0.015), chrome, bevel_width=0.005)


def seat(name, x, y, mats):
    leather, stitch, trim = mats
    base = cube(name, (x, y, 1.12), (0.50, 0.31, 0.12), leather, bevel_width=0.085)
    back = cube(name + "_back", (x - 0.32, y, 1.43), (0.18, 0.31, 0.34), leather, rotation=(0.0, math.radians(-8), 0.0), bevel_width=0.10)
    head = cube(name + "_headrest", (x - 0.48, y, 1.78), (0.11, 0.22, 0.14), leather, bevel_width=0.065)
    for yy in (y - 0.20, y + 0.20):
        cube(name + "_stitch", (x, yy, 1.23), (0.36, 0.008, 0.008), stitch, bevel_width=0.004)
    return base, back, head


def interior_detail(mats):
    leather, stitch, trim, screen, chrome = mats
    cube("dash_main", (0.92, 0.0, 1.56), (0.82, 0.94, 0.12), trim, bevel_width=0.055)
    cube("dash_pad", (0.58, 0.0, 1.73), (1.20, 0.91, 0.055), leather, bevel_width=0.035)
    cube("instrument_cluster", (0.65, -0.36, 1.82), (0.25, 0.23, 0.055), screen, bevel_width=0.03)
    cube("infotainment_screen", (1.08, 0.0, 1.84), (0.10, 0.42, 0.23), screen, bevel_width=0.035, rotation=(0.0, math.radians(-10), 0.0))
    cube("center_console", (0.05, 0.0, 1.30), (0.72, 0.24, 0.09), trim, bevel_width=0.045)
    cube("console_bridge", (-0.55, 0.0, 1.24), (0.42, 0.20, 0.10), leather, bevel_width=0.045)
    cylinder("gear_selector", (0.48, 0.0, 1.48), 0.065, 0.16, chrome, rotation=(0.0, 0.0, 0.0), vertices=32, bevel_width=0.015)
    torus("steering_wheel", (0.63, -0.55, 1.52), 0.27, 0.045, chrome)
    cube("steering_hub", (0.63, -0.55, 1.52), (0.06, 0.055, 0.06), trim, bevel_width=0.015)
    for angle in (0.0, math.radians(120), math.radians(240)):
        cube("steering_spoke", (0.63 + 0.12 * math.cos(angle), -0.55, 1.52 + 0.12 * math.sin(angle)), (0.035, 0.035, 0.12), chrome, rotation=(0.0, angle, 0.0), bevel_width=0.008)
    seat("driver_seat", -0.42, -0.53, (leather, stitch, trim))
    seat("passenger_seat", -0.42, 0.53, (leather, stitch, trim))
    for side in (-1, 1):
        cube(f"door_panel_{'l' if side < 0 else 'r'}", (-0.55, side * 0.96, 1.24), (0.78, 0.07, 0.35), leather, rotation=(0.0, math.radians(side * 4), 0.0), bevel_width=0.04)
        cube(f"door_handle_{'int_l' if side < 0 else 'int_r'}", (-0.12, side * 1.04, 1.46), (0.18, 0.025, 0.025), chrome, bevel_width=0.012)
    for side in (-1, 1):
        cylinder(f"door_speaker_{side}", (-0.75, side * 1.045, 1.06), 0.14, 0.025, trim, vertices=48, bevel_width=0.01)
    for y in (-0.20, 0.20):
        cube("center_vent", (1.16, y, 1.72), (0.07, 0.12, 0.018), chrome, bevel_width=0.008)
    cube("glovebox_seam", (0.82, 0.62, 1.43), (0.48, 0.012, 0.010), stitch, bevel_width=0.004)


def build_car():
    paint = material("CarPaint", (0.018, 0.075, 0.145), 0.93, 0.16, coat=0.92)
    paint2 = material("CarPaintAccent", (0.055, 0.16, 0.30), 0.88, 0.19, coat=0.75)
    trim = material("BlackTrim", (0.003, 0.006, 0.010), 0.72, 0.23, coat=0.25)
    glass = material("AutomotiveGlass", (0.012, 0.028, 0.045), 0.05, 0.08, transmission=0.55, coat=0.25)
    chrome = material("Chrome", (0.44, 0.50, 0.57), 0.98, 0.09, coat=0.35)
    tire = material("Tire", (0.006, 0.008, 0.010), 0.0, 0.52)
    rim = material("MachinedRim", (0.22, 0.27, 0.34), 0.98, 0.12)
    brake = material("Brake", (0.55, 0.025, 0.018), 0.30, 0.25)
    head = material("Headlight", (0.72, 0.90, 1.0), 0.05, 0.07, emission=(0.20, 0.55, 1.0))
    tail = material("Taillight", (1.0, 0.015, 0.008), 0.05, 0.09, emission=(0.85, 0.015, 0.008))
    leather = material("InteriorLeather", (0.035, 0.042, 0.050), 0.0, 0.48)
    stitch = material("InteriorStitch", (0.58, 0.62, 0.68), 0.15, 0.38)
    screen = material("Display", (0.005, 0.025, 0.055), 0.10, 0.12, emission=(0.03, 0.12, 0.28))
    floor = material("StudioFloor", (0.028, 0.036, 0.050), 0.25, 0.25)
    backdrop = material("StudioBackdrop", (0.045, 0.055, 0.072), 0.05, 0.46)

    body = loft_body(paint)
    cut_wheel_wells(body)
    greenhouse(glass, trim, paint2)
    wheel_mats = (tire, rim, brake, chrome)
    for x, prefix in ((2.35, "f"), (-2.35, "r")):
        for side, suffix in ((-1, "l"), (1, "r")):
            wheel(x, side, wheel_mats, prefix + suffix)
            fender_arch(x, side, trim, prefix + suffix)

    light_cluster((paint2, trim, chrome, head, tail))
    exterior_detail(paint2, trim, chrome)
    interior_detail((leather, stitch, trim, screen, chrome))

    # Ground and a curved-feeling studio backdrop: wide shots now contain context instead
    # of a giant black void.
    bpy.ops.mesh.primitive_plane_add(size=70, location=(0, 0, 0))
    studio_floor = bpy.context.object
    studio_floor.name = "studio_floor"
    studio_floor.data.materials.append(floor)

    bpy.ops.mesh.primitive_plane_add(size=70, location=(0, 24, 13), rotation=(math.radians(90), 0, 0))
    studio_backdrop = bpy.context.object
    studio_backdrop.name = "studio_backdrop"
    studio_backdrop.data.materials.append(backdrop)

    # A low platform makes the wheel contact and ground reflection readable.
    cube("display_plinth", (0, 0, 0.13), (5.2, 2.5, 0.13), trim, bevel_width=0.12)

    return {
        "body_shell": body,
        "materials": [paint, paint2, trim, glass, chrome, tire, rim, brake, head, tail, leather, stitch, screen],
        "floor": studio_floor,
        "backdrop": studio_backdrop,
    }


def hide_for_interior():
    # The outer shell is hidden only for the interior camera; the dedicated cockpit
    # remains fully 3D and is never replaced by a flat plate.
    for name in (
        "body_shell", "greenhouse_shell", "left_side_glass", "right_side_glass",
        "windshield_glass", "rear_glass", "roof_panel",
        "a_pillar_-1", "a_pillar_1", "b_pillar_-1", "b_pillar_1",
        "front_bumper", "rear_bumper", "front_lip", "rear_diffuser",
        "front_grille", "display_plinth",
    ):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_render = True
    for obj in bpy.data.objects:
        if obj.type == "MESH" and ("lamp" in obj.name or "wheel_" in obj.name or "tire_" in obj.name or "rim_" in obj.name or "spoke_" in obj.name or "hub_" in obj.name or "brake_" in obj.name):
            obj.hide_render = True


def set_camera(camera_name, width, height, scene_id):
    cameras = {
        "front_3q": ((8.2, -10.8, 3.0), (0.45, 0.0, 1.05), 58),
        "rear_3q": ((-8.1, 10.2, 3.0), (-0.35, 0.0, 1.05), 58),
        "front_close": ((7.2, -7.2, 2.15), (1.55, -0.05, 1.10), 68),
        "rear_close": ((-7.0, 6.9, 2.25), (-1.55, 0.05, 1.08), 68),
        "low_angle": ((10.2, -14.5, 0.82), (0.70, 0.0, 0.88), 63),
        "three_quarter_high": ((8.9, -10.0, 5.9), (0.10, 0.0, 1.05), 60),
        "side_profile": ((0.0, -14.6, 2.45), (-0.20, 0.0, 1.05), 64),
        "wide_scene": ((12.8, -18.0, 7.0), (0.0, 0.0, 0.95), 54),
        "interior": ((0.15, -2.05, 1.52), (0.85, -0.02, 1.50), 48),
    }
    pos, target, lens = cameras.get(camera_name, cameras["front_3q"])
    if height > width:
        # Portrait is composed independently rather than scaling the landscape camera
        # around the origin. Blender's vertical sensor fit changes the FOV, so the camera
        # must be closer to the intended target to preserve subject scale.
        if camera_name == "wide_scene":
            pos = (8.4, -12.8, 6.4)
            target = (0.0, 0.0, 1.0)
            lens = 58
        elif camera_name == "side_profile":
            pos = (0.0, -11.8, 2.55)
            target = (0.0, 0.0, 1.02)
            lens = 58
        elif camera_name == "interior":
            pos = (0.35, -1.72, 1.50)
            target = (0.92, -0.05, 1.50)
            lens = 42
        else:
            target = (target[0], target[1], target[2] + 0.05)
            p = Vector(pos)
            t = Vector(target)
            pos = tuple(t + (p - t) * 0.72)
            lens = max(48, lens - 4)

    data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(cam)
    data.lens = lens
    data.sensor_width = 36
    data.sensor_fit = "VERTICAL" if height > width else "HORIZONTAL"
    data.clip_start = 0.05
    data.clip_end = 200.0
    cam.location = Vector(pos)

    # Deterministic micro-variation without changing the authored composition.
    phase = ((scene_id * 17) % 7) - 3
    cam.location += Vector((0.045 * phase, 0.035 * ((scene_id // 7) % 3), 0.018 * ((scene_id % 5) - 2)))
    direction = Vector(target) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    if camera_name in {"front_close", "rear_close", "interior"}:
        data.dof.use_dof = True
        data.dof.focus_distance = max(1.0, direction.length * 0.86)
        data.dof.aperture_fstop = 4.2
    return cam


def lights(camera_name, scene_id, mats):
    key, fill, rim = mats
    def area(name, loc, energy, size, color, target=(0.0, 0.0, 1.0)):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
        return obj

    idx = (scene_id - 1) % 8
    palettes = [
        ((1.0, 0.76, 0.50), (0.36, 0.58, 1.0)),
        ((0.52, 0.72, 1.0), (1.0, 0.44, 0.24)),
        ((0.86, 0.94, 1.0), (0.40, 0.64, 1.0)),
        ((1.0, 0.52, 0.34), (0.46, 0.68, 1.0)),
        ((1.0, 0.82, 0.56), (0.32, 0.54, 0.92)),
        ((0.58, 0.82, 1.0), (1.0, 0.58, 0.30)),
        ((0.92, 0.96, 1.0), (0.44, 0.66, 1.0)),
        ((1.0, 0.64, 0.36), (0.50, 0.72, 1.0)),
    ]
    key_color, fill_color = palettes[idx]
    area("key_light", (5.0, -7.0, 7.0), 1750, 5.5, key_color, (0, 0, 1.0))
    area("fill_light", (-5.5, -3.0, 4.2), 820, 5.0, fill_color, (0, 0, 1.0))
    area("rim_light", (-1.0, 6.0, 5.6), 1500, 3.8, (1.0, 0.24 + idx * 0.015, 0.12), (0, 0, 1.0))
    area("top_light", (0, 0, 9.0), 1050, 5.0, (1.0, 1.0, 1.0), (0, 0, 0.8))
    area("front_soft_light", (7.0, -10.0, 2.6), 720, 4.5, (0.62, 0.78, 1.0), (0, 0, 1.0))
    if camera_name == "wide_scene":
        area("wide_light_key", (-7.0, -9.0, 9.0), 1350, 9.0, (0.86, 0.94, 1.0), (0, 0, 0.8))
        area("wide_light_fill", (8.0, 6.0, 6.0), 620, 7.0, (1.0, 0.42, 0.18), (0, 0, 1.0))
    if camera_name == "interior":
        area("cabin_key", (1.7, -1.6, 2.7), 2500, 2.0, (1.0, 0.68, 0.40), (0.8, -0.05, 1.5))
        area("cabin_fill", (-1.0, 1.2, 2.3), 1900, 2.6, (0.28, 0.54, 1.0), (0.8, 0.0, 1.5))
        area("cabin_top", (0.0, 0.0, 3.0), 1300, 1.8, (1.0, 0.92, 0.80), (0.8, 0.0, 1.4))
        area("cabin_screen", (1.5, -0.1, 2.1), 850, 1.0, (0.30, 0.68, 1.0), (1.0, 0.0, 1.8))
        area("cabin_floor", (0.0, -0.1, 0.45), 500, 2.4, (0.22, 0.42, 0.72), (0.8, 0.0, 1.2))


def configure_scene(width, height):
    scene = bpy.context.scene
    engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.fps = 30
    # Keep temporal CI deterministic and fast without changing production defaults.
    # EEVEE's render sampling is the dominant cost on headless runners.
    sample_override = _os.getenv("BLENDER_RENDER_SAMPLES", "").strip() if "_os" in globals() else os.getenv("BLENDER_RENDER_SAMPLES", "").strip()
    if sample_override:
        try:
            samples = max(1, min(128, int(sample_override)))
            eevee = getattr(scene, "eevee", None)
            if eevee is not None and hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = samples
        except (TypeError, ValueError):
            pass
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("AutomotiveWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.018, 0.024, 0.034, 1)
        bg.inputs["Strength"].default_value = 0.32
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.25


def scene_contract(camera_name):
    if camera_name == "interior":
        return "interior_cockpit_v2"
    if camera_name == "wide_scene":
        return "wide_environment_v2"
    return "exterior_automotive_v2"


def render_scene(output: Path, metadata: Path, width: int, height: int, camera_name: str, scene_id: int, topic: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_car()
    configure_scene(width, height)
    if camera_name == "interior":
        hide_for_interior()
    camera_obj = set_camera(camera_name, width, height, scene_id)
    bpy.context.scene.camera = camera_obj
    lights(camera_name, scene_id, (None, None, None))
    bpy.context.scene.render.filepath = str(Path(output).resolve())
    bpy.ops.render.render(write_still=True)

    names = {obj.name for obj in bpy.context.scene.objects}
    if camera_name == "interior":
        required = {
            "dash_main", "instrument_cluster", "infotainment_screen", "center_console",
            "steering_wheel", "driver_seat", "passenger_seat", "door_panel_l", "door_panel_r",
            "center_vent",
        }
    elif camera_name == "wide_scene":
        required = {"studio_floor", "studio_backdrop", "wide_light_key", "wide_light_fill"}
    else:
        required = {
            "body_shell", "front_bumper", "rear_bumper",
            "wheel_fl_arch", "wheel_fr_arch", "wheel_rl_arch", "wheel_rr_arch",
            "headlamp_l", "headlamp_r", "tail_lamp_l", "tail_lamp_r", "front_grille",
            "tire_fl", "tire_fr", "tire_rl", "tire_rr",
            "rim_fl", "rim_fr", "rim_rl", "rim_rr",
            "brake_fl", "brake_fr", "brake_rl", "brake_rr",
        }
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"VISUAL CONTRACT FAILED: {camera_name} missing objects: {missing}")
    meta = {
        "renderer": "blender_eevee_automotive_v4",
        "scene_id": scene_id,
        "camera": camera_name,
        "resolution": [width, height],
        "topic": topic,
        "geometry": "procedural_automotive_coupe_v4",
        "asset_external": False,
        "scene_contract": scene_contract(camera_name),
        "required_objects": sorted(required),
        "object_count": len(names),
    }
    Path(metadata).write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# Production extension: persistent asset preparation + true temporal motion.
# The authored v4 procedural body remains the asset source, but it is built once,
# stored as a Blender file, reused across all scenes, and never regenerated per shot.
import hashlib as _hashlib
import json as _json
import os as _os


def _load_asset_profile(path: Path) -> dict:
    data = _json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") if isinstance(data, dict) else None
    name = _os.getenv("AUTOMOTIVE_PROFILE", "premium_coupe")
    profile = profiles.get(name) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise RuntimeError(f"Unknown automotive profile: {name}")
    return profile


def _apply_asset_profile(profile: dict) -> None:
    paint = profile.get("paint", {})
    paint_material = bpy.data.materials.get("CarPaint")
    accent_material = bpy.data.materials.get("CarPaintAccent")
    if paint_material and paint.get("base"):
        node = _node(paint_material)
        if node and "Base Color" in node.inputs:
            node.inputs["Base Color"].default_value = (*map(float, paint["base"]), 1.0)
        if node and "Metallic" in node.inputs:
            node.inputs["Metallic"].default_value = float(paint.get("metallic", 0.93))
        if node and "Roughness" in node.inputs:
            node.inputs["Roughness"].default_value = float(paint.get("roughness", 0.16))
    if accent_material and paint.get("accent"):
        node = _node(accent_material)
        if node and "Base Color" in node.inputs:
            node.inputs["Base Color"].default_value = (*map(float, paint["accent"]), 1.0)

    wheels = profile.get("wheels", {})
    brake = bpy.data.materials.get("Brake")
    if brake and wheels.get("brake_color"):
        node = _node(brake)
        if node and "Base Color" in node.inputs:
            node.inputs["Base Color"].default_value = (*map(float, wheels["brake_color"]), 1.0)
    rim = bpy.data.materials.get("MachinedRim")
    if rim and wheels.get("rim_roughness") is not None:
        node = _node(rim)
        if node and "Roughness" in node.inputs:
            node.inputs["Roughness"].default_value = float(wheels["rim_roughness"])

    visible_spokes = int(wheels.get("visible_spokes", 10))
    if visible_spokes not in {5, 10, 12}:
        raise RuntimeError("Automotive profile visible_spokes must be 5, 10, or 12")
    for obj in bpy.data.objects:
        if obj.name.startswith("spoke_"):
            try:
                index = int(obj.name.rsplit("_", 1)[-1])
            except ValueError:
                continue
            obj.hide_render = index >= visible_spokes

    lighting = profile.get("lighting", {})
    world = bpy.context.scene.world
    if world and world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = float(lighting.get("background_strength", 0.32))


def build_persistent_asset(output: Path, metadata: Path, profile_path: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    profile = _load_asset_profile(profile_path)
    build_car()
    configure_scene(1920, 1080)
    _apply_asset_profile(profile)
    # Bake authored modifiers once into the persistent asset. This preserves the
    # authored geometry while removing per-frame Boolean/bevel evaluation overhead.
    bpy.context.view_layer.update()
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or not obj.modifiers:
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        for mod in list(obj.modifiers):
            if mod.type in {"BEVEL", "BOOLEAN"}:
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except RuntimeError:
                    pass
        obj.select_set(False)
    scene = bpy.context.scene
    scene["ace_asset_version"] = "automotive-coupe-v4-persistent"
    scene["ace_profile"] = _os.getenv("AUTOMOTIVE_PROFILE", "premium_coupe")
    scene["ace_asset_external"] = False
    bpy.ops.wm.save_as_mainfile(filepath=str(output.resolve()))
    digest = _hashlib.sha256(output.read_bytes()).hexdigest()
    metadata.write_text(
        _json.dumps(
            {
                "asset": str(output),
                "sha256": digest,
                "profile": scene["ace_profile"],
                "external": False,
                "builder": "local_blender_procedural_v4",
                "object_count": len(bpy.context.scene.objects),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _look_at(obj, target: Vector) -> None:
    direction = target - obj.location
    if direction.length < 1e-5:
        return
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _animate_camera(cam, camera_name: str, scene_id: int, duration: float, fps: int, profile: dict) -> int:
    scene = bpy.context.scene
    end = max(2, int(round(max(0.5, duration) * fps)))
    target = Vector((0.0, 0.0, 1.05))
    if camera_name == "interior":
        target = Vector((0.85, -0.02, 1.50))
    base = cam.location.copy()
    base_vector = base - target
    radius = max(1.0, base_vector.length)
    theta = __import__("math").atan2(base_vector.y, base_vector.x)
    orbit = __import__("math").radians(float(profile.get("motion", {}).get("orbit_degrees", 4.0)))
    dolly = float(profile.get("motion", {}).get("dolly_ratio", 0.045))
    direction = 1.0 if scene_id % 2 else -1.0
    base_lens = float(cam.data.lens)

    for frame, fraction in ((1, 0.0), (end // 2, 0.5), (end, 1.0)):
        angle = theta + direction * orbit * (fraction - 0.5)
        scale = 1.0 - dolly * (fraction - 0.5)
        cam.location = target + Vector(
            (
                __import__("math").cos(angle) * radius * scale,
                __import__("math").sin(angle) * radius * scale,
                base.z + 0.16 * __import__("math").sin(__import__("math").pi * fraction + scene_id * 0.17),
            )
        )
        _look_at(cam, target + Vector((0.0, 0.0, 0.03 * __import__("math").sin(__import__("math").pi * fraction)))
        )
        cam.data.lens = base_lens * (1.0 + 0.025 * __import__("math").sin(__import__("math").pi * fraction))
        cam.keyframe_insert(data_path="location", frame=frame)
        cam.keyframe_insert(data_path="rotation_euler", frame=frame)
        cam.data.keyframe_insert(data_path="lens", frame=frame)
    return end


def _animate_lights(end: int, profile: dict) -> None:
    multiplier = float(profile.get("lighting", {}).get("energy_multiplier", 1.0))
    lights = [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT"]
    for index, obj in enumerate(lights):
        base = float(obj.data.energy) * multiplier
        obj.data.energy = base * 0.96
        obj.data.keyframe_insert(data_path="energy", frame=1)
        obj.data.energy = base * (1.04 + (index % 3) * 0.02)
        obj.data.keyframe_insert(data_path="energy", frame=max(2, end // 2))
        obj.data.energy = base
        obj.data.keyframe_insert(data_path="energy", frame=end)


def _render_temporal_animation(path: Path, end: int, fps: int) -> None:
    # Do not rely on Blender's FFMPEG animation writer: the GitHub runner's
    # Blender build can finish the render without materializing the requested
    # MP4. Render a deterministic PNG sequence, then mux it with the system
    # ffmpeg. This also makes the artifact independently inspectable.
    scene = bpy.context.scene
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = end
    frame_dir = path.parent / (path.stem + "_frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(frame_dir / "frame_")
    bpy.ops.render.render(animation=True)

    frames = sorted(frame_dir.glob("frame_*.png"))
    if len(frames) < 2:
        raise RuntimeError(f"Temporal Blender produced only {len(frames)} frames")
    import subprocess as _subprocess
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-an", str(path),
    ]
    proc = _subprocess.run(cmd, stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Temporal ffmpeg mux failed: {proc.stdout[-4000:]}")
    # Keep the smoke artifact small and deterministic; the MP4 is the contract.
    for frame in frames:
        frame.unlink(missing_ok=True)
    try:
        frame_dir.rmdir()
    except OSError:
        pass


def render_scene(
    output: Path,
    metadata: Path,
    width: int,
    height: int,
    camera_name: str,
    scene_id: int,
    topic: str,
):
    asset_path = Path(_os.getenv("AUTOMOTIVE_ASSET_PATH", "")).expanduser()
    profile_path = Path(
        _os.getenv(
            "AUTOMOTIVE_PROFILE_PATH",
            str(Path(__file__).resolve().parents[1] / "config" / "automotive_profiles.json"),
        )
    )
    if asset_path.is_file():
        bpy.ops.wm.open_mainfile(filepath=str(asset_path.resolve()))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_car()

    profile = _load_asset_profile(profile_path)
    configure_scene(width, height)
    _apply_asset_profile(profile)
    if camera_name == "interior":
        hide_for_interior()
    camera_obj = set_camera(camera_name, width, height, scene_id)
    bpy.context.scene.camera = camera_obj
    lights(camera_name, scene_id, (None, None, None))
    animation_duration = max(0.25, float(_os.getenv("AUTOMOTIVE_RENDER_DURATION", "18.0")))
    # An explicit environment FPS is a test/CI contract and must override the profile.
    fps = int(_os.getenv("AUTOMOTIVE_MOTION_FPS", str(profile.get("motion", {}).get("fps", 15))))
    fps = max(8, min(30, fps))
    end = _animate_camera(camera_obj, camera_name, scene_id, animation_duration, fps, profile)
    _animate_lights(end, profile)

    output.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_set(1)
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.filepath = str(output.resolve())
    bpy.ops.render.render(write_still=True)

    motion_output = Path(_os.getenv("AUTOMOTIVE_RENDER_MOTION_OUTPUT", "")).expanduser()
    motion_enabled = _os.getenv("AUTOMOTIVE_RENDER_MOTION", "0").strip() in {"1", "true", "yes"}
    if motion_enabled:
        if not motion_output:
            raise RuntimeError("True temporal rendering requested but no motion output path was supplied")
        motion_output.parent.mkdir(parents=True, exist_ok=True)
        _render_temporal_animation(motion_output, end, fps)
        if not motion_output.is_file():
            raise RuntimeError(f"Blender produced no temporal video: {motion_output}")
        # A tiny low-resolution smoke video can legitimately be <32 KiB. Validate
        # the media contract (stream + duration + dimensions) instead of file size.
        probe = _subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,nb_frames,duration",
                "-of", "json", str(motion_output),
            ], stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT, text=True,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"Temporal video failed ffprobe: {motion_output}\\n{probe.stdout[-4000:]}")
        try:
            payload = _json.loads(probe.stdout)
            stream = (payload.get("streams") or [])[0]
            width = int(stream.get("width", 0)); height = int(stream.get("height", 0))
            duration = float(stream.get("duration") or 0.0)
            frames = int(stream.get("nb_frames") or 0)
        except (ValueError, TypeError, IndexError, _json.JSONDecodeError) as exc:
            raise RuntimeError(f"Temporal video ffprobe returned invalid metadata: {probe.stdout[-4000:]}") from exc
        if width < 1 or height < 1 or duration <= 0.0 or frames < 2:
            raise RuntimeError(f"Temporal video contract failed: {payload}")

    names = {obj.name for obj in bpy.context.scene.objects}
    if camera_name == "interior":
        required = {"dash_main", "instrument_cluster", "infotainment_screen", "center_console", "steering_wheel", "driver_seat", "passenger_seat", "door_panel_l", "door_panel_r", "center_vent"}
    elif camera_name == "wide_scene":
        required = {"studio_floor", "studio_backdrop", "wide_light_key", "wide_light_fill"}
    else:
        required = {"body_shell", "front_bumper", "rear_bumper", "wheel_fl_arch", "wheel_fr_arch", "wheel_rl_arch", "wheel_rr_arch", "headlamp_l", "headlamp_r", "tail_lamp_l", "tail_lamp_r", "front_grille", "tire_fl", "tire_fr", "tire_rl", "tire_rr", "rim_fl", "rim_fr", "rim_rl", "rim_rr", "brake_fl", "brake_fr", "brake_rl", "brake_rr"}
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"VISUAL CONTRACT FAILED: {camera_name} missing objects: {missing}")

    digest = _hashlib.sha256(asset_path.read_bytes()).hexdigest() if asset_path.is_file() else None
    meta = {
        "renderer": "blender_eevee_automotive_v5_temporal",
        "scene_id": scene_id,
        "camera": camera_name,
        "resolution": [width, height],
        "topic": topic,
        "geometry": "persistent_automotive_coupe_v4",
        "asset_external": False,
        "asset_path": str(asset_path) if asset_path.is_file() else None,
        "asset_sha256": digest,
        "profile": _os.getenv("AUTOMOTIVE_PROFILE", "premium_coupe"),
        "scene_contract": scene_contract(camera_name),
        "required_objects": sorted(required),
        "object_count": len(names),
        "motion": {
            "enabled": motion_enabled,
            "type": "blender_keyframed_temporal",
            "fps": fps,
            "frames": end,
            "duration": animation_duration,
        },
    }
    metadata.write_text(_json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
