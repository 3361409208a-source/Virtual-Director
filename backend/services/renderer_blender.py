"""
Blender (bpy) renderer — drop-in replacement for the Godot renderer.

Coordinate conversion
---------------------
sequence.json  (Godot convention):  X=right  Y=up   Z=forward(negative)
Blender:                            X=right  Z=up   Y=forward(positive = front)

Position :  seq(x, y, z) -> bpy( x, -z,  y)
Rotation :  seq_euler_deg(rx, ry, rz) -> bpy_euler_rad( rx_rad, rz_rad, ry_rad )

Usage
-----
Two modes, tried in order:
  1. Direct bpy import (pip install bpy)
  2. Subprocess: blender --background --python <this_file> -- <seq.json> <out.mp4>
"""

import json
import math
import os
import subprocess
import sys
import tempfile


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _p(d, dx=0.0, dy=0.0, dz=0.0):
    """seq position dict -> Blender (x, y, z)"""
    return (float(d.get("x", dx)), -float(d.get("z", dz)), float(d.get("y", dy)))


def _r(d):
    """seq rotation dict (degrees) -> Blender euler (radians)"""
    rx = math.radians(float(d.get("x", 0)))
    ry = math.radians(float(d.get("y", 0)))
    rz = math.radians(float(d.get("z", 0)))
    return (rx, rz, ry)


def _c(d, r=0.7, g=0.7, b=0.7):
    return (float(d.get("r", r)), float(d.get("g", g)), float(d.get("b", b)), 1.0)


def _lerp(a, b, t):
    return a + (b - a) * t


# ── Actor position interpolation ──────────────────────────────────────────────

def _bake_actor_positions(actor_tracks: dict, total_frames: int, fps: int) -> dict:
    """
    Pre-compute (bpy_x, bpy_y, bpy_z) for every actor at every frame.
    Returns  { actor_id: [ (x,y,z), ... ] }  indexed by frame 0..total_frames
    """
    result = {}
    for aid, kfs in actor_tracks.items():
        if not kfs:
            result[aid] = [(0, 0, 0)] * (total_frames + 1)
            continue
        positions = []
        for f in range(total_frames + 1):
            t = f / fps
            # find surrounding keyframes
            prev = kfs[0]
            nxt  = kfs[0]
            for kf in kfs:
                if float(kf.get("time", 0)) <= t:
                    prev = kf
                else:
                    nxt = kf
                    break
            t0 = float(prev.get("time", 0))
            t1 = float(nxt.get("time", t0))
            alpha = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            alpha = max(0.0, min(1.0, alpha))
            p0 = _p(prev.get("position", {}))
            p1 = _p(nxt.get("position", {}))
            pos = (_lerp(p0[0], p1[0], alpha),
                   _lerp(p0[1], p1[1], alpha),
                   _lerp(p0[2], p1[2], alpha))
            positions.append(pos)
        result[aid] = positions
    return result


# ── Main Blender scene builder ────────────────────────────────────────────────

def _build_and_render(sequence: dict, mp4_path: str) -> None:
    import bpy                       # noqa: imported inside so outer code can still load the module
    from mathutils import Vector, Euler

    meta     = sequence.get("meta", {})
    fps      = int(meta.get("fps", 24))
    duration = float(meta.get("total_duration", 5.0))
    total_frames = int(duration * fps)

    # ── 0. Reset scene ──────────────────────────────────────────────────────
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials,
                bpy.data.lights, bpy.data.cameras):
        for item in list(blk):
            blk.remove(item)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = total_frames
    scene.render.fps  = fps

    # ── 1. Render settings ──────────────────────────────────────────────────
    scene.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"
    scene.render.resolution_x = 1152
    scene.render.resolution_y = 648
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec  = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = mp4_path

    # ── 2. World / sky ──────────────────────────────────────────────────────
    s_setup = sequence.get("scene_setup", {})
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()

    sky_d   = s_setup.get("sky", {})
    top_c   = _c(sky_d.get("top_color",     {"r": 0.18, "g": 0.36, "b": 0.72}), 0.18, 0.36, 0.72)
    hor_c   = _c(sky_d.get("horizon_color", {"r": 0.60, "g": 0.72, "b": 0.88}), 0.60, 0.72, 0.88)

    bg_node  = wnt.nodes.new("ShaderNodeBackground")
    mix_node = wnt.nodes.new("ShaderNodeMixRGB")
    grad     = wnt.nodes.new("ShaderNodeTexGradient")
    coord    = wnt.nodes.new("ShaderNodeTexCoord")
    out_node = wnt.nodes.new("ShaderNodeOutputWorld")

    grad.gradient_type = "SPHERICAL"
    wnt.links.new(coord.outputs["Generated"],  grad.inputs["Vector"])
    wnt.links.new(grad.outputs["Color"],       mix_node.inputs["Fac"])
    mix_node.inputs["Color1"].default_value = hor_c
    mix_node.inputs["Color2"].default_value = top_c
    wnt.links.new(mix_node.outputs["Color"],   bg_node.inputs["Color"])
    wnt.links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])

    ambient_energy = max(float(s_setup.get("ambient_energy", 0.5)), 0.35)
    bg_node.inputs["Strength"].default_value = ambient_energy

    # ── 3. Sun light ────────────────────────────────────────────────────────
    sun_d = s_setup.get("sun", {})
    if sun_d.get("enabled", True):
        sun_data = bpy.data.lights.new("Sun", type="SUN")
        sun_obj  = bpy.data.objects.new("Sun", sun_data)
        scene.collection.objects.link(sun_obj)
        ed = sun_d.get("euler_degrees", {"x": -55, "y": -30, "z": 0})
        sun_obj.rotation_euler = Euler(_r(ed))
        col = sun_d.get("color", {"r": 1.0, "g": 0.95, "b": 0.8})
        sun_data.color  = _c(col)[:3]
        sun_data.energy = float(sun_d.get("energy", 1.5))
        sun_data.use_shadow = True

    # ── 4. Fill light (ambient point) ───────────────────────────────────────
    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_obj  = bpy.data.objects.new("FillLight", fill_data)
    scene.collection.objects.link(fill_obj)
    fill_obj.location = (10, 10, 15)
    fill_data.energy  = 200
    fill_data.color   = (0.85, 0.88, 1.0)
    fill_data.size    = 8.0

    # ── 5. Ground ────────────────────────────────────────────────────────────
    gnd_d = s_setup.get("ground", {})
    if gnd_d.get("enabled", True):
        size = float(gnd_d.get("size", 60.0))
        bpy.ops.mesh.primitive_plane_add(size=size)
        gnd = bpy.context.active_object
        gnd.name = "Ground"
        mat = _pbr_mat("GroundMat", gnd_d.get("color", {"r": 0.3, "g": 0.3, "b": 0.3}), roughness=1.0)
        gnd.data.materials.append(mat)

    # ── 6. Props ─────────────────────────────────────────────────────────────
    for prop in s_setup.get("props", []):
        _spawn_primitive(prop, scene, prefix="prop")

    # ── 7. Asset manifest & actors ───────────────────────────────────────────
    asset_manifest = sequence.get("asset_manifest", {})
    actor_objects  = {}  # actor_id -> root bpy object

    for actor in sequence.get("actors", []):
        aid  = str(actor.get("id", ""))
        ipos = actor.get("initial_position", {})
        irot = actor.get("initial_rotation", {})

        manifest = asset_manifest.get(aid)
        if manifest and isinstance(manifest, dict) and manifest.get("type") == "composite":
            root, _ = _build_composite(manifest.get("parts", []), aid, scene)
        else:
            root = _fallback_box(aid, scene)

        root.location      = Vector(_p(ipos))
        root.rotation_euler = Euler(_r(irot))
        actor_objects[aid]  = root

    # ── 8. Actor animation tracks ────────────────────────────────────────────
    actor_tracks = sequence.get("actor_tracks", {})
    for aid, kfs in actor_tracks.items():
        obj = actor_objects.get(aid)
        if not obj or not kfs:
            continue
        for kf in kfs:
            t    = float(kf.get("time", 0))
            fr   = int(round(t * fps)) + 1
            pos  = _p(kf.get("position", {}))
            rot  = _r(kf.get("rotation", {}))
            scene.frame_set(fr)
            obj.location       = Vector(pos)
            obj.rotation_euler = Euler(rot)
            obj.keyframe_insert("location",       frame=fr)
            obj.keyframe_insert("rotation_euler", frame=fr)

    # ── 9. Camera ────────────────────────────────────────────────────────────
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj  = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_data.lens = 35  # 50mm equivalent in 1152x648

    baked_positions = _bake_actor_positions(actor_tracks, total_frames, fps)
    cam_track = sequence.get("camera_track", [])

    if not cam_track:
        cam_obj.location       = Vector((0, 10, 3))
        cam_obj.rotation_euler = Euler((math.radians(80), 0, math.pi))
    else:
        _bake_camera(cam_obj, cam_data, cam_track, baked_positions,
                     actor_objects, total_frames, fps, scene)

    # ── 10. Render ───────────────────────────────────────────────────────────
    print(f"[BlenderRenderer] Rendering {total_frames} frames @ {fps}fps -> {mp4_path}")
    bpy.ops.render.render(animation=True)
    print("[BlenderRenderer] Done.")


# ── Camera baking ─────────────────────────────────────────────────────────────

def _bake_camera(cam_obj, cam_data, cam_track, baked_pos, actor_objects,
                 total_frames, fps, scene):
    import bpy
    from mathutils import Vector, Euler, Quaternion

    def _actor_pos_at(aid, frame_idx):
        pts = baked_pos.get(str(aid), [])
        if not pts:
            return Vector((0, 0, 0))
        idx = max(0, min(len(pts) - 1, frame_idx))
        return Vector(pts[idx])

    def _centroid(frame_idx):
        positions = [_actor_pos_at(aid, frame_idx) for aid in baked_pos]
        if not positions:
            return Vector((0, 0, 0))
        return sum(positions, Vector()) / len(positions)

    orbit_angle = 0.0
    seg_idx = 0

    for frame in range(1, total_frames + 1):
        t  = (frame - 1) / fps
        fi = frame - 1   # 0-based frame index for baked_pos

        # advance segment
        while seg_idx + 1 < len(cam_track) and \
              float(cam_track[seg_idx + 1].get("time", 0)) <= t:
            seg_idx += 1
            if str(cam_track[seg_idx].get("transition", "smooth")) == "cut":
                orbit_angle = 0.0

        seg  = cam_track[seg_idx]
        mode = str(seg.get("mode", "follow"))
        fov  = float(seg.get("fov", 65))
        # bpy camera uses sensor/lens, convert fov to focal length
        # focal_len = sensor_width / (2 * tan(fov/2))
        sensor = cam_data.sensor_width  # default 36mm
        cam_data.lens = sensor / (2.0 * math.tan(math.radians(fov) / 2.0))

        target_id  = str(seg.get("target_id",  ""))
        look_at_id = str(seg.get("look_at_id", target_id))

        tpos    = _actor_pos_at(target_id, fi) if target_id else _centroid(fi)
        look_at = _actor_pos_at(look_at_id, fi) if look_at_id else tpos

        if mode == "follow":
            off_d  = seg.get("offset", {"x": 0, "y": 2, "z": 7})
            offset = Vector(_p(off_d, 0, 2, 7))
            cam_pos = tpos + offset

        elif mode == "orbit":
            radius = float(seg.get("radius", 7.0))
            height = float(seg.get("height", 3.0))
            speed  = float(seg.get("orbit_speed", 0.6))
            orbit_angle += speed / fps
            cam_pos = tpos + Vector((
                math.cos(orbit_angle) * radius,
                math.sin(orbit_angle) * radius,
                height
            ))

        elif mode == "static_look":
            pos_d   = seg.get("position", {"x": 8, "y": 1.5, "z": 0})
            cam_pos = Vector(_p(pos_d, 8, 1.5, 0))

        elif mode == "wide_look":
            pos_d   = seg.get("position", {"x": 0, "y": 15, "z": 12})
            cam_pos = Vector(_p(pos_d, 0, 15, 12))
            look_at = _centroid(fi)

        else:
            cam_pos = tpos + Vector((0, 7, 2))

        cam_obj.location = cam_pos
        _point_camera_at(cam_obj, look_at + Vector((0, 0, 0.9)))

        # Only insert keyframe every 3 frames for performance; always at transitions
        is_transition = any(
            int(round(float(s.get("time", 0)) * fps)) + 1 == frame
            for s in cam_track
        )
        if frame % 3 == 0 or is_transition:
            cam_obj.keyframe_insert("location",       frame=frame)
            cam_obj.keyframe_insert("rotation_euler", frame=frame)

    # Smooth interpolation
    if cam_obj.animation_data and cam_obj.animation_data.action:
        for fc in cam_obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"


def _point_camera_at(cam_obj, target: "Vector"):
    """Rotate camera to look at target position."""
    from mathutils import Vector
    direction = (target - cam_obj.location).normalized()
    if direction.length_squared < 1e-6:
        return
    # Blender camera looks down -Z by default
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot_quat.to_euler()


# ── Scene object helpers ──────────────────────────────────────────────────────

def _pbr_mat(name: str, color_dict: dict, roughness=0.6, metallic=0.0):
    import bpy
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = _c(color_dict)
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["Metallic"].default_value   = metallic
    return mat


def _add_primitive(shape: str, size_dict: dict, color_dict: dict,
                   pos_dict: dict, rot_dict: dict, name: str, scene):
    import bpy
    from mathutils import Vector, Euler

    sx = float(size_dict.get("x", 1.0))
    sy = float(size_dict.get("y", 1.0))
    sz = float(size_dict.get("z", 1.0))

    if shape == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=sx * 0.5, segments=32, ring_count=16)
        obj = bpy.context.active_object
        bpy.ops.object.shade_smooth()
    elif shape == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=sx * 0.5, depth=sy)
        obj = bpy.context.active_object
        bpy.ops.object.shade_smooth()
    else:
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        obj.scale = (sx * 0.5, sz * 0.5, sy * 0.5)
        bpy.ops.object.transform_apply(scale=True)

    obj.name = name
    mat = _pbr_mat(f"mat_{name}", color_dict)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    obj.location       = Vector(_p(pos_dict))
    obj.rotation_euler = Euler(_r(rot_dict))
    return obj


def _spawn_primitive(pd: dict, scene, prefix="obj"):
    import bpy
    name  = str(pd.get("id", f"{prefix}_{id(pd)}"))
    shape = str(pd.get("shape", "box"))
    return _add_primitive(
        shape,
        pd.get("size",     {"x": 1, "y": 1, "z": 1}),
        pd.get("color",    {"r": 0.6, "g": 0.5, "b": 0.4}),
        pd.get("position", {"x": 0,  "y": 0,  "z": 0}),
        {},
        name, scene
    )


def _build_composite(parts: list, actor_id: str, scene) -> tuple:
    """Build composite actor; returns (root_empty, {part_name: obj})"""
    import bpy
    from mathutils import Vector, Euler

    root = bpy.data.objects.new(actor_id, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.1
    scene.collection.objects.link(root)

    part_map = {"": root}

    for p in parts:
        if not isinstance(p, dict):
            continue
        p_name      = str(p.get("name",        f"part_{len(part_map)}"))
        parent_name = str(p.get("parent_name", ""))
        shape       = str(p.get("shape",       "box"))
        size        = p.get("size",     {"x": 1,   "y": 1,   "z": 1})
        color       = p.get("color",    {"r": 0.8,  "g": 0.8,  "b": 0.8})
        pos         = p.get("position", {"x": 0,   "y": 0,   "z": 0})
        rot         = p.get("rotation", {"x": 0,   "y": 0,   "z": 0})

        unique_name = f"{actor_id}__{p_name}"
        obj = _add_primitive(shape, size, color, pos, rot, unique_name, scene)

        parent_obj = part_map.get(parent_name, root)
        obj.parent = parent_obj
        # Clear parent-induced transform
        if parent_obj is not root:
            obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()

        part_map[p_name] = obj

    return root, part_map


def _fallback_box(actor_id: str, scene) -> "bpy.types.Object":
    import bpy
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = actor_id
    mat = _pbr_mat(f"mat_{actor_id}", {"r": 0.5, "g": 0.5, "b": 0.55})
    obj.data.materials.append(mat)
    scene.collection.objects.link(obj) if obj.name not in scene.collection.objects else None
    return obj


# ── Public API ────────────────────────────────────────────────────────────────

def do_blender(sequence: dict, mp4_path: str) -> None:
    """
    Render sequence dict to mp4_path.
    Tries direct bpy import first; falls back to blender subprocess.
    """
    os.makedirs(os.path.dirname(mp4_path), exist_ok=True)

    try:
        import bpy  # noqa
        print("[BlenderRenderer] Using bpy pip module.")
        _build_and_render(sequence, mp4_path)
        return
    except ImportError:
        pass

    # Fallback: call blender executable
    from backend.config import BLENDER_EXECUTABLE
    if not BLENDER_EXECUTABLE or not os.path.exists(BLENDER_EXECUTABLE):
        raise RuntimeError(
            "bpy not installed and BLENDER_EXECUTABLE not found.\n"
            "Run: pip install bpy   OR set BLENDER_EXECUTABLE in .env"
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as f:
        json.dump(sequence, f, ensure_ascii=False)
        seq_path = f.name

    script_path = os.path.abspath(__file__)
    try:
        result = subprocess.run(
            [BLENDER_EXECUTABLE, "--background", "--python", script_path,
             "--", seq_path, mp4_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        print(f"[Blender subprocess] returncode: {result.returncode}")
        if result.stdout:
            print(result.stdout[-2000:])
        if result.returncode != 0:
            raise RuntimeError(f"Blender 渲染失败:\n{result.stderr[-600:]}")
    finally:
        os.unlink(seq_path)


# ── Subprocess entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    # Called by: blender --background --python renderer_blender.py -- seq.json out.mp4
    argv = sys.argv
    try:
        sep = argv.index("--")
        seq_path = argv[sep + 1]
        out_path = argv[sep + 2]
    except (ValueError, IndexError):
        print("Usage: blender --background --python renderer_blender.py -- seq.json out.mp4")
        sys.exit(1)

    with open(seq_path, "r", encoding="utf-8") as f:
        sequence = json.load(f)

    _build_and_render(sequence, out_path)
