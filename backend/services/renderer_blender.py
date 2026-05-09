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

def _build_and_render(sequence: dict, mp4_path: str, progress_cb=None) -> None:
    import bpy                       # noqa: imported inside so outer code can still load the module
    from mathutils import Vector, Euler

    import json as _json2
    def _pf(v, t=dict):
        if isinstance(v, str):
            try: v = _json2.loads(v)
            except Exception: pass
        return v if isinstance(v, t) else (t() if t is dict else [])
    meta      = _pf(sequence.get("meta", {}))
    fps       = min(int(meta.get("fps", 24)), 12)   # cap at 12fps — CYCLES CPU budget
    duration  = float(meta.get("total_duration", 5.0))
    godot_dir = str(meta.get("godot_dir", ""))
    total_frames = int(duration * fps)

    # ── 0. Reset scene (data API — no context required) ───────────────────
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for blk in (bpy.data.meshes, bpy.data.materials,
                bpy.data.lights, bpy.data.cameras):
        for item in list(blk):
            blk.remove(item)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = total_frames
    scene.render.fps  = fps

    # ── 1. Render settings (CYCLES CPU — headless-safe) ────────────────────
    scene.render.engine              = "CYCLES"
    scene.cycles.device              = "CPU"
    scene.cycles.samples             = 32          # more samples, no denoiser noise
    scene.cycles.use_denoising       = False       # skip OIDN — saves per-frame post cost
    scene.render.use_persistent_data = True        # reuse BVH/shaders across frames
    scene.render.threads_mode        = "AUTO"      # use all CPU cores
    scene.render.resolution_x        = 640         # 640x360 — 56% less pixels vs 960x540
    scene.render.resolution_y        = 360
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode  = "RGB"
    # Frames written here; ffmpeg assembles MP4 after render
    frames_dir = mp4_path.replace(".mp4", "_frames")
    os.makedirs(frames_dir, exist_ok=True)
    # Blender appends frame number as 4-digit zero-padded (e.g. frame_0001.png)
    scene.render.filepath = os.path.join(frames_dir, "frame_")

    # ── 2. World / sky ──────────────────────────────────────────────────────
    import json as _json

    def _ensure_dict(v, default=None):
        if default is None:
            default = {}
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return default
        return v if isinstance(v, dict) else default

    def _ensure_list(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if isinstance(v, list) else []

    s_setup = _ensure_dict(sequence.get("scene_setup", {}))
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()

    sky_d   = s_setup.get("sky", {})
    top_c   = _c(sky_d.get("top_color",     {"r": 0.18, "g": 0.36, "b": 0.72}), 0.18, 0.36, 0.72)
    hor_c   = _c(sky_d.get("horizon_color", {"r": 0.60, "g": 0.72, "b": 0.88}), 0.60, 0.72, 0.88)

    bg_node  = wnt.nodes.new("ShaderNodeBackground")
    out_node = wnt.nodes.new("ShaderNodeOutputWorld")
    # Sky gradient via Mix node (name changed in Blender 4.x)
    try:
        mix_node = wnt.nodes.new("ShaderNodeMixRGB")
        mix_node.inputs["Color1"].default_value = hor_c
        mix_node.inputs["Color2"].default_value = top_c
        mix_fac_input  = mix_node.inputs["Fac"]
        mix_color_out  = mix_node.outputs["Color"]
    except Exception:
        mix_node = wnt.nodes.new("ShaderNodeMix")
        mix_node.data_type = "RGBA"
        mix_node.inputs[6].default_value = hor_c
        mix_node.inputs[7].default_value = top_c
        mix_fac_input  = mix_node.inputs[0]
        mix_color_out  = mix_node.outputs[2]
    grad  = wnt.nodes.new("ShaderNodeTexGradient")
    coord = wnt.nodes.new("ShaderNodeTexCoord")
    grad.gradient_type = "SPHERICAL"
    wnt.links.new(coord.outputs["Generated"], grad.inputs["Vector"])
    wnt.links.new(grad.outputs["Color"],      mix_fac_input)
    wnt.links.new(mix_color_out,              bg_node.inputs["Color"])
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
        gnd_mesh = _make_plane_mesh("GroundMesh", size)
        gnd = bpy.data.objects.new("Ground", gnd_mesh)
        scene.collection.objects.link(gnd)
        base_col = gnd_d.get("color", {"r": 0.3, "g": 0.3, "b": 0.3})
        mat = _checker_ground_mat("GroundMat", base_col)
        gnd.data.materials.append(mat)

    # ── 6. Props ─────────────────────────────────────────────────────────────
    for prop in s_setup.get("props", []):
        _spawn_primitive(prop, scene, prefix="prop")

    # ── 7. Asset manifest & actors ───────────────────────────────────────────
    asset_manifest = _pf(sequence.get("asset_manifest", {}))
    actor_objects  = {}  # actor_id -> root bpy object
    actor_parts    = {}  # actor_id -> {part_name: bpy object}
    actor_types    = {}  # actor_id -> type string

    for actor in _pf(sequence.get("actors", []), list):
        aid  = str(actor.get("id", ""))
        ipos = actor.get("initial_position", {})
        irot = actor.get("initial_rotation", {})
        actor_types[aid] = str(actor.get("type", "box"))

        manifest = asset_manifest.get(aid)
        if manifest and isinstance(manifest, dict):
            mtype = manifest.get("type", "")
            if mtype == "composite":
                root, part_map = _build_composite(manifest.get("parts", []), aid, scene)
                actor_parts[aid] = part_map
            elif mtype == "downloaded":
                abs_path = manifest.get("abs_path", "")
                if not abs_path:
                    rel = manifest.get("path", "")
                    abs_path = os.path.join(godot_dir, rel) if godot_dir and rel else rel
                root = _import_glb_actor(abs_path, aid, scene) or _fallback_box(aid, scene)
            else:
                root = _fallback_box(aid, scene)
        else:
            root = _fallback_box(aid, scene)

        root.location      = Vector(_p(ipos))
        root.rotation_euler = Euler(_r(irot))
        actor_objects[aid]  = root

    # ── 8. Actor animation tracks ────────────────────────────────────────────
    actor_tracks = _pf(sequence.get("actor_tracks", {}))
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

    # ── 8b. Sub-tracks & procedural bone animations ───────────────────────────
    for aid, kfs in actor_tracks.items():
        part_map = actor_parts.get(aid)
        if not part_map or not kfs:
            continue
        atype = actor_types.get(aid, "box")

        _apply_sub_tracks(kfs, part_map, fps, scene)

        if atype == "humanoid":
            _apply_walk_cycle(kfs, part_map, fps, scene)
        elif atype in ("car", "plane"):
            _apply_wheel_rotation(kfs, part_map, fps, scene)

    # ── 9. Camera ────────────────────────────────────────────────────────────
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj  = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_data.lens = 35  # 50mm equivalent in 1152x648

    baked_positions = _bake_actor_positions(actor_tracks, total_frames, fps)
    cam_track = _pf(sequence.get("camera_track", []), list)

    if not cam_track:
        cam_obj.location       = Vector((0, 10, 3))
        cam_obj.rotation_euler = Euler((math.radians(80), 0, math.pi))
    else:
        _bake_camera(cam_obj, cam_data, cam_track, baked_positions,
                     actor_objects, total_frames, fps, scene)

    # ── 10. Render frames ─────────────────────────────────────────────────────
    print(f"[BlenderRenderer] Rendering {total_frames} frames @ {fps}fps -> {frames_dir}")

    bpy.ops.render.render(animation=True)
    print("[BlenderRenderer] Frames done. Assembling MP4 with ffmpeg…")

    # ── 11. Assemble MP4 ─────────────────────────────────────────────────────
    # Blender writes frame_0001.png … so start_number=1
    frame_pattern = os.path.join(frames_dir, "frame_%04d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", frame_pattern,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        mp4_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 合成失败:\n{result.stderr[-400:]}")
    print(f"[BlenderRenderer] MP4 saved -> {mp4_path}")

    # ── 12. Cleanup frames ───────────────────────────────────────────────────
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)


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

    # Smooth interpolation (non-critical — API changed in Blender 4.4+)
    try:
        action = cam_obj.animation_data.action if cam_obj.animation_data else None
        if action:
            fcurves = getattr(action, "fcurves", None)
            if fcurves is None:
                # Blender 4.4+ layered action: layers > strips > channelbag > fcurves
                fcurves = []
                for layer in getattr(action, "layers", []):
                    for strip in getattr(layer, "strips", []):
                        for cb in getattr(strip, "channelbags", []):
                            fcurves.extend(getattr(cb, "fcurves", []))
            for fc in (fcurves or []):
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
    except Exception:
        pass


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


def _checker_ground_mat(name: str, color_dict: dict):
    """Checkerboard ground material — provides visual motion reference."""
    import bpy
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    bsdf     = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out      = nt.nodes.new("ShaderNodeOutputMaterial")
    checker  = nt.nodes.new("ShaderNodeTexChecker")
    mapping  = nt.nodes.new("ShaderNodeMapping")
    coord    = nt.nodes.new("ShaderNodeTexCoord")

    # 2-meter grid squares
    mapping.inputs["Scale"].default_value = (0.5, 0.5, 0.5)
    checker.inputs["Scale"].default_value = 1.0

    # Checker colors: base color and a slightly darker version
    r = float(color_dict.get("r", 0.3))
    g = float(color_dict.get("g", 0.3))
    b = float(color_dict.get("b", 0.3))
    checker.inputs["Color1"].default_value = (r,       g,       b,       1.0)
    checker.inputs["Color2"].default_value = (r * 0.6, g * 0.6, b * 0.6, 1.0)

    nt.links.new(coord.outputs["Generated"],   mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"],    checker.inputs["Vector"])
    nt.links.new(checker.outputs["Color"],     bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],         out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 1.0
    return mat


def _make_plane_mesh(name: str, size: float):
    """Ground plane mesh via bmesh (no ops)."""
    import bpy, bmesh
    mesh = bpy.data.meshes.new(name)
    bm   = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2.0)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _add_primitive(shape: str, size_dict: dict, color_dict: dict,
                   pos_dict: dict, rot_dict: dict, name: str, scene):
    """Create mesh object via bmesh — no bpy.ops context required."""
    import bpy, bmesh
    from mathutils import Vector, Euler

    sx = float(size_dict.get("x", 1.0))
    sy = float(size_dict.get("y", 1.0))
    sz = float(size_dict.get("z", 1.0))

    mesh = bpy.data.meshes.new(name)
    bm   = bmesh.new()

    if shape == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=sx * 0.5)
        bm.to_mesh(mesh)
        bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = True
    elif shape == "cylinder":
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                              segments=16, radius1=sx * 0.5, radius2=sx * 0.5, depth=sy)
        bm.to_mesh(mesh)
        bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = True
    else:  # box
        bmesh.ops.create_cube(bm, size=2.0)
        bmesh.ops.scale(bm, vec=Vector((sx * 0.5, sz * 0.5, sy * 0.5)), verts=list(bm.verts))
        bm.to_mesh(mesh)
        bm.free()

    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)

    mat = _pbr_mat(f"mat_{name}", color_dict)
    mesh.materials.append(mat)

    obj.location       = Vector(_p(pos_dict))
    obj.rotation_euler = Euler(_r(rot_dict))
    return obj


def _spawn_primitive(pd: dict, scene, prefix="obj"):
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


# ── Procedural bone / part animations ────────────────────────────────────────

def _find_part(part_map: dict, candidates: list):
    """Return first matching part object from a priority-ordered candidate list."""
    for c in candidates:
        if c in part_map:
            return part_map[c]
        for k in part_map:
            if c in k.lower():
                return part_map[k]
    return None


def _vec_dist(p0: dict, p1: dict) -> float:
    import math
    dx = float(p1.get("x", 0)) - float(p0.get("x", 0))
    dy = float(p1.get("y", 0)) - float(p0.get("y", 0))
    dz = float(p1.get("z", 0)) - float(p0.get("z", 0))
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _apply_walk_cycle(kfs: list, part_map: dict, fps: int, scene) -> None:
    """Generate procedural walk/run/ragdoll limb animation for a humanoid composite actor."""
    import math
    from mathutils import Euler

    leg_l  = _find_part(part_map, ["left_leg", "leg_l", "l_leg", "thigh_l", "lower_leg_l"])
    leg_r  = _find_part(part_map, ["right_leg", "leg_r", "r_leg", "thigh_r", "lower_leg_r"])
    arm_l  = _find_part(part_map, ["left_arm", "arm_l", "l_arm", "upper_arm_l", "forearm_l"])
    arm_r  = _find_part(part_map, ["right_arm", "arm_r", "r_arm", "upper_arm_r", "forearm_r"])
    spine  = _find_part(part_map, ["spine", "torso", "chest", "body", "trunk"])

    if not any([leg_l, leg_r, arm_l, arm_r]):
        return

    walk_freq = 1.8   # steps/sec at walking pace

    for i, kf in enumerate(kfs):
        t0         = float(kf.get("time", 0))
        bone_anim  = kf.get("bone_anim", "")
        t1_kf      = kfs[i + 1] if i + 1 < len(kfs) else None
        t1         = float(t1_kf.get("time", t0 + 1.0)) if t1_kf else t0 + 1.0

        # Infer speed from position delta when bone_anim is not explicit
        if bone_anim not in ("walk", "run", "ragdoll"):
            if t1_kf and t1 > t0:
                dist  = _vec_dist(kf.get("position", {}), t1_kf.get("position", {}))
                speed = dist / (t1 - t0)
                if speed >= 3.0:
                    bone_anim = "run"
                elif speed >= 0.4:
                    bone_anim = "walk"
                else:
                    continue
            else:
                continue

        if bone_anim == "idle":
            continue

        freq      = walk_freq * (1.7 if bone_anim == "run" else 1.0)
        amplitude = 38.0 if bone_anim == "run" else 28.0
        arm_amp   = amplitude * 0.55

        for f in range(int(t0 * fps), int(t1 * fps) + 1):
            curr_t = f / fps
            phase  = curr_t * 2 * math.pi * freq
            fr     = f + 1

            if bone_anim == "ragdoll":
                rnd = math.sin(curr_t * 7.3) * 45
                if leg_l:
                    leg_l.rotation_euler = Euler((math.radians(rnd * 1.1), math.radians(rnd * 0.4), 0))
                    leg_l.keyframe_insert("rotation_euler", frame=fr)
                if leg_r:
                    leg_r.rotation_euler = Euler((math.radians(-rnd * 0.9), math.radians(-rnd * 0.5), 0))
                    leg_r.keyframe_insert("rotation_euler", frame=fr)
                if arm_l:
                    arm_l.rotation_euler = Euler((math.radians(-rnd * 0.8), 0, math.radians(rnd * 0.6)))
                    arm_l.keyframe_insert("rotation_euler", frame=fr)
                if arm_r:
                    arm_r.rotation_euler = Euler((math.radians(rnd * 0.7), 0, math.radians(-rnd * 0.6)))
                    arm_r.keyframe_insert("rotation_euler", frame=fr)
            else:
                scene.frame_set(fr)
                if leg_l:
                    leg_l.rotation_euler = Euler((math.radians(math.sin(phase) * amplitude), 0, 0))
                    leg_l.keyframe_insert("rotation_euler", frame=fr)
                if leg_r:
                    leg_r.rotation_euler = Euler((math.radians(-math.sin(phase) * amplitude), 0, 0))
                    leg_r.keyframe_insert("rotation_euler", frame=fr)
                if arm_l:
                    arm_l.rotation_euler = Euler((math.radians(-math.sin(phase) * arm_amp), 0, 0))
                    arm_l.keyframe_insert("rotation_euler", frame=fr)
                if arm_r:
                    arm_r.rotation_euler = Euler((math.radians(math.sin(phase) * arm_amp), 0, 0))
                    arm_r.keyframe_insert("rotation_euler", frame=fr)
                if spine:
                    spine.rotation_euler = Euler((math.radians(5 + math.sin(phase * 0.5) * 3), 0, 0))
                    spine.keyframe_insert("rotation_euler", frame=fr)


def _apply_wheel_rotation(kfs: list, part_map: dict, fps: int, scene) -> None:
    """Auto-generate wheel spin keyframes for car composite actors.
    Only runs if the AI did NOT already populate sub_tracks for wheel parts.
    """
    import math
    from mathutils import Euler

    wheel_parts = {}
    for pname, pobj in part_map.items():
        ln = pname.lower()
        if "wheel" in ln or "tire" in ln or "tyre" in ln:
            wheel_parts[pname] = pobj

    if not wheel_parts:
        return

    # Skip if AI already provided manual sub_tracks for any wheel
    for kf in kfs:
        for wn in kf.get("sub_tracks", {}):
            if wn in wheel_parts:
                return

    wheel_radius   = 0.38   # metres (approximate)
    deg_per_meter  = 360.0 / (2 * math.pi * wheel_radius)
    cumulative_rot = 0.0
    prev_z         = None

    for kf in kfs:
        t     = float(kf.get("time", 0))
        curr_z = float(kf.get("position", {}).get("z", 0))
        if prev_z is not None:
            dz = curr_z - prev_z
            cumulative_rot += dz * deg_per_meter

        fr = int(round(t * fps)) + 1
        scene.frame_set(fr)
        for wobj in wheel_parts.values():
            wobj.rotation_euler = Euler((math.radians(cumulative_rot), 0, 0))
            wobj.keyframe_insert("rotation_euler", frame=fr)

        prev_z = curr_z


def _apply_sub_tracks(kfs: list, part_map: dict, fps: int, scene) -> None:
    """Apply AI-specified sub_track per-part animations from keyframes."""
    from mathutils import Vector, Euler

    for kf in kfs:
        sub = kf.get("sub_tracks")
        if not sub or not isinstance(sub, dict):
            continue
        t  = float(kf.get("time", 0))
        fr = int(round(t * fps)) + 1
        scene.frame_set(fr)
        for part_name, ptransform in sub.items():
            pobj = part_map.get(part_name)
            if not pobj or not isinstance(ptransform, dict):
                continue
            ppos = ptransform.get("position")
            prot = ptransform.get("rotation")
            if ppos and isinstance(ppos, dict):
                pobj.location = Vector(_p(ppos))
                pobj.keyframe_insert("location", frame=fr)
            if prot and isinstance(prot, dict):
                pobj.rotation_euler = Euler(_r(prot))
                pobj.keyframe_insert("rotation_euler", frame=fr)


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

        part_map[p_name] = obj

    return root, part_map


def _fallback_box(actor_id: str, scene) -> "bpy.types.Object":
    return _add_primitive("box", {"x": 1, "y": 1, "z": 1},
                          {"r": 0.5, "g": 0.5, "b": 0.55},
                          {}, {}, actor_id, scene)


def _import_glb_actor(glb_path: str, actor_id: str, scene) -> "bpy.types.Object | None":
    """Import a GLB file into the Blender scene and return a root Empty parenting all imports."""
    import bpy
    if not glb_path or not os.path.exists(glb_path):
        print(f"[BlenderRenderer] GLB not found: {glb_path}")
        return None
    try:
        existing_names = set(bpy.data.objects.keys())

        # Try context-override import (Blender 3.2+); fall back to bare call
        try:
            with bpy.context.temp_override():
                bpy.ops.import_scene.gltf(filepath=glb_path)
        except Exception:
            bpy.ops.import_scene.gltf(filepath=glb_path)

        new_objs = [o for o in bpy.data.objects if o.name not in existing_names]
        if not new_objs:
            print(f"[BlenderRenderer] GLTF import produced no objects: {glb_path}")
            return None

        # Ensure all imported objects belong to our scene collection
        for obj in new_objs:
            if obj.name not in scene.collection.objects:
                scene.collection.objects.link(obj)

        # Build a root Empty to parent everything, for uniform transform handling
        root = bpy.data.objects.new(actor_id, None)
        root.empty_display_type = "PLAIN_AXES"
        root.empty_display_size = 0.1
        scene.collection.objects.link(root)

        new_set = {o.name for o in new_objs}
        for obj in new_objs:
            if obj.parent is None or obj.parent.name not in new_set:
                obj.parent = root

        print(f"[BlenderRenderer] Imported GLB '{os.path.basename(glb_path)}' → {len(new_objs)} objects")
        return root
    except Exception as e:
        print(f"[BlenderRenderer] GLB import failed for {actor_id}: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def do_blender(sequence: dict, mp4_path: str, progress_cb=None) -> None:
    """
    Render sequence dict to mp4_path.
    Tries direct bpy import first; falls back to blender subprocess.
    progress_cb(frame: int, total: int) is called after each frame is written.
    """
    os.makedirs(os.path.dirname(mp4_path), exist_ok=True)

    try:
        import bpy  # noqa
        print("[BlenderRenderer] Using bpy pip module.")
        _build_and_render(sequence, mp4_path, progress_cb)
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
