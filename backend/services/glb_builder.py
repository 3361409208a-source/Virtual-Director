"""
Convert a composite asset manifest (list of primitive parts) into
a binary GLB file using pygltflib.

Each part schema:
{
  "name": "torso",
  "shape": "box" | "sphere" | "cylinder" | "cone" | "capsule" | "lathe" | "extrude",
  "size":     {"x": 0.5, "y": 0.9, "z": 0.3},   # bounding box extents (for basic shapes)
  "position": {"x": 0.0, "y": 0.5, "z": 0.0},
  "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},   # euler degrees, optional
  "color":    {"r": 0.8, "g": 0.2, "b": 0.2, "a": 1.0},  # 0-1 float RGBA, a optional
  "metallic":  0.1,      # 0-1, default 0.1
  "roughness": 0.8,      # 0-1, default 0.8
  "emissive":  {"r": 0, "g": 1, "b": 0, "intensity": 2.0},  # optional self-illumination
  "scale":     {"x": 1.0, "y": 1.0, "z": 1.0},   # optional non-uniform scale
  "texture":   "brick" | "wood" | "fabric" | "metal_brush" | "checker" | "dragon_scale" | "tile",  # optional procedural texture
  # Lathe shape: profile points revolved around Y axis
  "profile":   [{"y": 0, "r": 0.3}, {"y": 0.5, "r": 0.5}, ...],  # for shape="lathe"
  # Extrude shape: 2D polygon extruded along Z
  "cross_section": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, ...],  # for shape="extrude"
  "extrude_depth": 0.5,  # for shape="extrude"
  # CSG boolean operations
  "csg": {"operation": "subtract", "tool": {<part_spec>}},  # subtract/intersect this tool shape
}
"""

import math
import struct
import io
import numpy as np
import pygltflib
import trimesh
from PIL import Image, ImageDraw


# ── Primitive mesh generators ─────────────────────────────────────────────────

def _box_mesh(sx: float, sy: float, sz: float):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    verts = np.array([
        # front
        [-hx, -hy,  hz], [ hx, -hy,  hz], [ hx,  hy,  hz], [-hx,  hy,  hz],
        # back
        [-hx, -hy, -hz], [ hx, -hy, -hz], [ hx,  hy, -hz], [-hx,  hy, -hz],
        # top
        [-hx,  hy, -hz], [ hx,  hy, -hz], [ hx,  hy,  hz], [-hx,  hy,  hz],
        # bottom
        [-hx, -hy, -hz], [ hx, -hy, -hz], [ hx, -hy,  hz], [-hx, -hy,  hz],
        # right
        [ hx, -hy, -hz], [ hx,  hy, -hz], [ hx,  hy,  hz], [ hx, -hy,  hz],
        # left
        [-hx, -hy, -hz], [-hx,  hy, -hz], [-hx,  hy,  hz], [-hx, -hy,  hz],
    ], dtype=np.float32)
    face = [0,1,2, 0,2,3]
    indices = np.array([f + i*4 for i in range(6) for f in face], dtype=np.uint16)
    return verts, indices


def _sphere_mesh(rx: float, ry: float, rz: float, rings: int = 12, segs: int = 16):
    verts = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([
                rx * math.sin(phi) * math.cos(theta),
                ry * math.cos(phi),
                rz * math.sin(phi) * math.sin(theta),
            ])
    verts = np.array(verts, dtype=np.float32)
    idx = []
    for i in range(rings):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            c = (i + 1) * segs + (j + 1) % segs
            d = (i + 1) * segs + j
            idx += [a, b, c, a, c, d]
    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


def _cone_mesh(sx: float, sy: float, sz: float, segs: int = 16):
    """Cone along Y axis, bounding box [sx, sy, sz], tip at top."""
    rx, rz = sx / 2, sz / 2
    h = sy / 2
    verts = []
    idx = []
    # Base ring + center
    for i in range(segs):
        a = 2 * math.pi * i / segs
        verts.append([rx * math.cos(a), -h, rz * math.sin(a)])
    base_center = len(verts)
    verts.append([0, -h, 0])
    # Tip
    tip = len(verts)
    verts.append([0, h, 0])
    verts = np.array(verts, dtype=np.float32)
    # Side faces
    for i in range(segs):
        j = (i + 1) % segs
        idx += [i, j, tip]
    # Base cap
    for i in range(segs):
        j = (i + 1) % segs
        idx += [base_center, j, i]
    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


def _capsule_mesh(sx: float, sy: float, sz: float, rings: int = 8, segs: int = 16):
    """Capsule along Y axis: cylinder body + hemisphere caps. bounding box [sx, sy, sz]."""
    rx, rz = sx / 2, sz / 2
    h = sy / 2  # total half-height
    cap_h = min(min(rx, rz), h)  # cap height
    body_h = h - cap_h  # cylinder body half-height
    verts = []
    idx = []
    # Bottom hemisphere
    for i in range(rings + 1):
        phi = math.pi * i / (2 * rings)  # 0 to pi/2 (bottom cap inverted)
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([
                rx * math.sin(phi) * math.cos(theta),
                -(body_h + cap_h * math.cos(phi)),
                rz * math.sin(phi) * math.sin(theta),
            ])
    # Top hemisphere
    for i in range(rings + 1):
        phi = math.pi * i / (2 * rings)  # 0 to pi/2
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([
                rx * math.sin(phi) * math.cos(theta),
                body_h + cap_h * math.cos(phi),
                rz * math.sin(phi) * math.sin(theta),
            ])
    verts = np.array(verts, dtype=np.float32)
    # Bottom hemisphere indices
    n_bot = (rings + 1) * segs
    for i in range(rings):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            c = (i + 1) * segs + (j + 1) % segs
            d = (i + 1) * segs + j
            idx += [a, c, b, a, d, c]
    # Top hemisphere indices
    off = n_bot
    for i in range(rings):
        for j in range(segs):
            a = off + i * segs + j
            b = off + i * segs + (j + 1) % segs
            c = off + (i + 1) * segs + (j + 1) % segs
            d = off + (i + 1) * segs + j
            idx += [a, b, c, a, c, d]
    # Connect bottom ring to top ring (side)
    bot_ring_start = rings * segs  # last ring of bottom hemisphere
    top_ring_start = off  # first ring of top hemisphere
    for j in range(segs):
        jn = (j + 1) % segs
        a = bot_ring_start + j
        b = bot_ring_start + jn
        c = top_ring_start + jn
        d = top_ring_start + j
        idx += [a, c, b, a, d, c]
    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


def _cylinder_mesh(sx: float, sy: float, sz: float, segs: int = 16):
    """Capped cylinder along Y axis, bounding box [sx, sy, sz]."""
    rx, rz = sx / 2, sz / 2
    h = sy / 2
    top_verts, bot_verts, side_top, side_bot = [], [], [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        x, z = rx * math.cos(a), rz * math.sin(a)
        side_top.append([x,  h, z])
        side_bot.append([x, -h, z])
        top_verts.append([x,  h, z])
        bot_verts.append([x, -h, z])

    verts = side_top + side_bot + [[0, h, 0]] + top_verts + [[0, -h, 0]] + bot_verts
    verts = np.array(verts, dtype=np.float32)

    idx = []
    for i in range(segs):
        j = (i + 1) % segs
        idx += [i, j + segs, j, i, i + segs, j + segs]

    base_top = 2 * segs
    cap_center_top = base_top
    cap_start_top  = base_top + 1
    for i in range(segs):
        idx += [cap_center_top, cap_start_top + i, cap_start_top + (i+1) % segs]

    cap_center_bot = cap_start_top + segs
    cap_start_bot  = cap_center_bot + 1
    for i in range(segs):
        idx += [cap_center_bot, cap_start_bot + (i+1) % segs, cap_start_bot + i]

    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


# ── Lathe mesh (profile revolved around Y axis) ─────────────────────────────

def _lathe_mesh(profile: list[dict], segs: int = 24):
    """
    Revolve a 2D profile [{y, r}, ...] around the Y axis.
    Each point: y = height, r = radius from Y axis.
    """
    n_pts = len(profile)
    if n_pts < 2:
        raise ValueError("lathe profile needs at least 2 points")
    verts = []
    idx = []
    for i in range(n_pts):
        y = float(profile[i].get("y", 0))
        r = float(profile[i].get("r", 0))
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([r * math.cos(theta), y, r * math.sin(theta)])
    verts = np.array(verts, dtype=np.float32)
    for i in range(n_pts - 1):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            c = (i + 1) * segs + (j + 1) % segs
            d = (i + 1) * segs + j
            idx += [a, b, c, a, c, d]
    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


# ── Extrude mesh (2D polygon extruded along Z) ──────────────────────────────

def _extrude_mesh(cross_section: list[dict], depth: float):
    """
    Extrude a 2D polygon [{x, y}, ...] along Z axis by `depth`.
    Uses trimesh for robust polygon triangulation + extrusion.
    """
    n = len(cross_section)
    if n < 3:
        raise ValueError("extrude cross_section needs at least 3 points")
    pts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in cross_section]
    from shapely.geometry import Polygon as ShapelyPolygon
    polygon = ShapelyPolygon(pts)
    ext = trimesh.creation.extrude_polygon(polygon, depth)
    verts = np.ascontiguousarray(ext.vertices, dtype=np.float32)
    indices = np.ascontiguousarray(ext.faces.flatten(), dtype=np.uint16)
    return verts, indices


# ── Spline tube mesh (tube along 3D spline path) ────────────────────────────────

def _spline_tube_mesh(points: list[dict], radius: float = 0.05, segs: int = 8, interp: int = 24):
    """
    Create a tube along a 3D Catmull-Rom spline defined by control points.
    points: [{x, y, z}, ...] at least 2 points.
    radius: tube radius.
    segs: cross-section circle segments.
    interp: interpolation steps between each pair of control points.
    """
    n = len(points)
    if n < 2:
        raise ValueError("spline_tube needs at least 2 points")
    pts_3d = np.array([[float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))] for p in points], dtype=np.float32)

    # Catmull-Rom interpolation
    spline_pts = []
    for i in range(n - 1):
        p0 = pts_3d[max(i - 1, 0)]
        p1 = pts_3d[i]
        p2 = pts_3d[min(i + 1, n - 1)]
        p3 = pts_3d[min(i + 2, n - 1)]
        for t_i in range(interp):
            t = t_i / interp
            t2, t3 = t * t, t * t * t
            pt = 0.5 * ((2 * p1) +
                         (-p0 + p2) * t +
                         (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                         (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            spline_pts.append(pt)
    spline_pts.append(pts_3d[-1])
    spline_pts = np.array(spline_pts, dtype=np.float32)
    n_spline = len(spline_pts)

    # Build Frenet frames along the spline
    tangents = np.zeros_like(spline_pts)
    tangents[:-1] = spline_pts[1:] - spline_pts[:-1]
    tangents[-1] = tangents[-2]
    lengths = np.linalg.norm(tangents, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    tangents /= lengths

    # Initial normal = cross(tangent, up) or fallback
    up = np.array([0, 1, 0], dtype=np.float32)
    normals = np.zeros_like(spline_pts)
    binormals = np.zeros_like(spline_pts)
    for i in range(n_spline):
        t = tangents[i]
        if abs(np.dot(t, up)) > 0.99:
            up_local = np.array([1, 0, 0], dtype=np.float32)
        else:
            up_local = up
        n_vec = np.cross(t, up_local)
        n_len = np.linalg.norm(n_vec)
        if n_len < 1e-8:
            n_vec = np.array([1, 0, 0], dtype=np.float32)
        else:
            n_vec /= n_len
        normals[i] = n_vec
        binormals[i] = np.cross(t, n_vec)

    # Smooth normals (parallel transport approximation)
    for i in range(1, n_spline):
        b = np.cross(tangents[i - 1], tangents[i])
        b_len = np.linalg.norm(b)
        if b_len > 1e-8:
            angle = math.asin(min(b_len, 1.0))
            b /= b_len
            c, s = math.cos(angle), math.sin(angle)
            normals[i] = normals[i] * c + np.cross(b, normals[i]) * s + b * np.dot(b, normals[i]) * (1 - c)
            n_len = np.linalg.norm(normals[i])
            if n_len > 1e-8:
                normals[i] /= n_len
            binormals[i] = np.cross(tangents[i], normals[i])

    # Generate tube vertices
    verts = []
    for i in range(n_spline):
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            offset = normals[i] * math.cos(theta) * radius + binormals[i] * math.sin(theta) * radius
            verts.append(spline_pts[i] + offset)
    verts = np.array(verts, dtype=np.float32)

    # Indices
    idx = []
    for i in range(n_spline - 1):
        for j in range(segs):
            jn = (j + 1) % segs
            a = i * segs + j
            b = i * segs + jn
            c = (i + 1) * segs + jn
            d = (i + 1) * segs + j
            idx += [a, b, c, a, c, d]
    # Cap start
    center_s = len(verts)
    verts_list = list(verts)
    verts_list.append(spline_pts[0])
    for j in range(segs):
        jn = (j + 1) % segs
        idx += [center_s, j, jn]
    # Cap end
    center_e = len(verts_list)
    verts_list.append(spline_pts[-1])
    base_e = (n_spline - 1) * segs
    for j in range(segs):
        jn = (j + 1) % segs
        idx += [center_e, base_e + jn, base_e + j]
    verts = np.array(verts_list, dtype=np.float32)
    indices = np.array(idx, dtype=np.uint16)
    return verts, indices


# ── Deformed mesh (noise-displaced shape for organic surfaces) ────────────────

def _simple_noise_3d(x: float, y: float, z: float, seed: int = 0) -> float:
    """Simple hash-based pseudo-noise for vertex displacement."""
    n = int(x * 73 + y * 179 + z * 283 + seed * 37) & 0x7FFFFFFF
    n = ((n << 13) ^ n) & 0x7FFFFFFF
    return (1.0 - ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7FFFFFFF) / 1073741824.0) * 0.5


def _fbm_noise(x: float, y: float, z: float, octaves: int = 3, seed: int = 0) -> float:
    """Fractal Brownian Motion noise."""
    value = 0.0
    amplitude = 1.0
    frequency = 1.0
    for _ in range(octaves):
        value += amplitude * _simple_noise_3d(x * frequency, y * frequency, z * frequency, seed)
        amplitude *= 0.5
        frequency *= 2.0
        seed += 17
    return value


def _deformed_mesh(base_shape: str, size: dict, displacement: float = 0.15,
                   detail: int = 2, seed: int = 42, spikes: float = 0.0):
    """
    Create an organic deformed mesh by displacing vertices along normals.
    base_shape: 'sphere' | 'rock' (sphere with more displacement)
    size: {x, y, z} bounding box
    displacement: max displacement amount (fraction of size)
    detail: subdivision level for icosphere (1-4)
    spikes: extra spiky displacement (for thorns, crystals)
    """
    sx = float(size.get("x", 1.0))
    sy = float(size.get("y", 1.0))
    sz = float(size.get("z", 1.0))

    # Start from icosphere
    m = trimesh.creation.icosphere(subdivisions=detail)
    verts = m.vertices.copy()

    # Normalize to bounding box
    for i in range(len(verts)):
        v = verts[i]
        # Scale to ellipsoid
        v[0] *= sx / 2
        v[1] *= sy / 2
        v[2] *= sz / 2
        # Compute displacement along normal direction
        norm = np.linalg.norm(v)
        if norm > 1e-8:
            direction = v / norm
        else:
            direction = np.array([0, 1, 0])
        # Noise-based displacement
        noise_val = _fbm_noise(v[0] * 3, v[1] * 3, v[2] * 3, octaves=3, seed=seed)
        disp = displacement * min(sx, sy, sz) * 0.5 * noise_val
        # Add spike component
        if spikes > 0:
            spike_noise = _simple_noise_3d(v[0] * 8, v[1] * 8, v[2] * 8, seed + 100)
            if spike_noise > 0.6:
                disp += spikes * min(sx, sy, sz) * 0.3 * (spike_noise - 0.6) / 0.4
        verts[i] = v + direction * disp

    m.vertices = verts
    # Recompute normals
    m.fix_normals()
    verts = np.ascontiguousarray(m.vertices, dtype=np.float32)
    indices = np.ascontiguousarray(m.faces.flatten(), dtype=np.uint16)
    return verts, indices


# ── Tree mesh (procedural L-system tree) ──────────────────────────────────────

def _tree_mesh(config: dict):
    """
    Generate a procedural tree using recursive branching.
    config keys:
      trunk_height: float (default 3.0)
      trunk_radius: float (default 0.15)
      branch_levels: int (default 3, max 4)
      branch_count: int (default 3, branches per level)
      branch_spread: float (default 0.8, angle spread)
      branch_length_ratio: float (default 0.65, child/parent length)
      branch_radius_ratio: float (default 0.55, child/parent radius)
      leaf_type: 'sphere'|'cluster'|'none' (default 'sphere')
      leaf_size: float (default 0.3)
      leaf_color: dict (default green)
      trunk_color: dict (default brown)
      seed: int (default 42)
    Returns list of (verts, indices, color_dict) tuples for each part.
    """
    import random as _rng
    seed = int(config.get("seed", 42))
    _rng.seed(seed)

    trunk_h = float(config.get("trunk_height", 3.0))
    trunk_r = float(config.get("trunk_radius", 0.15))
    levels = min(int(config.get("branch_levels", 3)), 4)
    branch_count = int(config.get("branch_count", 3))
    spread = float(config.get("branch_spread", 0.8))
    len_ratio = float(config.get("branch_length_ratio", 0.65))
    rad_ratio = float(config.get("branch_radius_ratio", 0.55))
    leaf_type = str(config.get("leaf_type", "sphere"))
    leaf_size = float(config.get("leaf_size", 0.3))

    trunk_color = config.get("trunk_color", {"r": 0.4, "g": 0.25, "b": 0.1})
    leaf_color = config.get("leaf_color", {"r": 0.15, "g": 0.55, "b": 0.1})

    parts = []  # list of (verts, indices, color, name)

    def _add_cylinder_part(start, end, radius, color, name):
        """Add a tapered cylinder between two 3D points."""
        sx = radius * 2
        sy = float(np.linalg.norm(np.array(end) - np.array(start)))
        sz = radius * 2
        if sy < 0.01:
            return
        # Generate cylinder mesh
        segs = 8
        rx, rz = sx / 2, sz / 2
        h = sy / 2
        cv, ci = _cylinder_mesh(sx, sy, sz, segs=segs)
        # Compute rotation to align Y axis with (end-start) direction
        direction = np.array(end, dtype=np.float32) - np.array(start, dtype=np.float32)
        d_len = np.linalg.norm(direction)
        if d_len < 1e-8:
            return
        direction /= d_len
        # Default cylinder axis is Y
        up = np.array([0, 1, 0], dtype=np.float32)
        if abs(np.dot(direction, up)) > 0.999:
            rot_axis = np.array([1, 0, 0], dtype=np.float32)
            if direction[1] < 0:
                angle = math.pi
            else:
                angle = 0.0
        else:
            rot_axis = np.cross(up, direction)
            rot_axis /= np.linalg.norm(rot_axis)
            angle = math.acos(np.clip(np.dot(up, direction), -1, 1))
        # Rodrigues rotation
        K = np.array([[0, -rot_axis[2], rot_axis[1]],
                       [rot_axis[2], 0, -rot_axis[0]],
                       [-rot_axis[1], rot_axis[0], 0]], dtype=np.float32)
        R = np.eye(3, dtype=np.float32) + math.sin(angle) * K + (1 - math.cos(angle)) * (K @ K)
        # Apply rotation and translation
        center = (np.array(start, dtype=np.float32) + np.array(end, dtype=np.float32)) / 2
        for i in range(len(cv)):
            cv[i] = R @ cv[i] + center
        parts.append((cv, ci, color, name))

    def _branch(origin, direction, length, radius, level, name_prefix):
        """Recursively generate branches."""
        if level <= 0 or length < 0.05 or radius < 0.005:
            return
        end = [origin[i] + direction[i] * length for i in range(3)]
        _add_cylinder_part(origin, end, radius, trunk_color, f"{name_prefix}_L{level}")

        if level == 1 and leaf_type != "none":
            # Add leaf cluster at branch tip
            if leaf_type == "sphere":
                lv, li = _sphere_mesh(leaf_size, leaf_size, leaf_size, rings=6, segs=8)
                for i in range(len(lv)):
                    lv[i] = [lv[i][0] + end[0], lv[i][1] + end[1], lv[i][2] + end[2]]
                parts.append((lv, li, leaf_color, f"{name_prefix}_leaf"))
            elif leaf_type == "cluster":
                # Multiple small leaf spheres
                for li_idx in range(5):
                    offset = [_rng.uniform(-leaf_size, leaf_size) * 0.5,
                              _rng.uniform(-leaf_size * 0.3, leaf_size * 0.5),
                              _rng.uniform(-leaf_size, leaf_size) * 0.5]
                    ls = leaf_size * _rng.uniform(0.5, 1.0)
                    lv, li = _sphere_mesh(ls, ls, ls, rings=4, segs=6)
                    for i in range(len(lv)):
                        lv[i] = [lv[i][0] + end[0] + offset[0],
                                  lv[i][1] + end[1] + offset[1],
                                  lv[i][2] + end[2] + offset[2]]
                    parts.append((lv, li, leaf_color, f"{name_prefix}_leaf_{li_idx}"))
            return

        # Generate child branches
        for b in range(branch_count):
            angle_h = spread * _rng.uniform(0.5, 1.0)
            angle_around = 2 * math.pi * b / branch_count + _rng.uniform(-0.3, 0.3)
            # Rotate direction
            # Find perpendicular vectors
            if abs(direction[1]) > 0.99:
                perp1 = np.array([1, 0, 0], dtype=np.float32)
            else:
                perp1 = np.cross(direction, [0, 1, 0])
                perp1 /= np.linalg.norm(perp1)
            perp2 = np.cross(direction, perp1)
            perp2 /= np.linalg.norm(perp2)
            new_dir = (direction * math.cos(angle_h) +
                       perp1 * math.sin(angle_h) * math.cos(angle_around) +
                       perp2 * math.sin(angle_h) * math.sin(angle_around))
            new_dir = new_dir / np.linalg.norm(new_dir)
            # Slight upward bias
            new_dir[1] = max(new_dir[1], 0.1)
            new_dir = new_dir / np.linalg.norm(new_dir)
            _branch(end, new_dir, length * len_ratio * _rng.uniform(0.8, 1.1),
                    radius * rad_ratio, level - 1, f"{name_prefix}_b{b}")

    # Generate trunk
    trunk_origin = [0, 0, 0]
    trunk_end = [0, trunk_h, 0]
    _add_cylinder_part(trunk_origin, trunk_end, trunk_r, trunk_color, "trunk")

    # Generate branches from top of trunk
    for b in range(branch_count + 1):
        angle_h = spread * _rng.uniform(0.6, 1.0)
        angle_around = 2 * math.pi * b / (branch_count + 1) + _rng.uniform(-0.2, 0.2)
        direction = np.array([math.sin(angle_h) * math.cos(angle_around),
                              math.cos(angle_h),
                              math.sin(angle_h) * math.sin(angle_around)], dtype=np.float32)
        start_y = trunk_h * _rng.uniform(0.6, 0.95)
        start = [0, start_y, 0]
        branch_len = trunk_h * 0.5 * _rng.uniform(0.7, 1.0)
        _branch(start, direction, branch_len, trunk_r * 0.6, levels, f"branch_{b}")

    # Add canopy foliage or fruits at top
    fruit_count = int(config.get("fruit_count", 0))
    fruit_size  = float(config.get("fruit_size", 0.08))
    fruit_color = config.get("fruit_color", {"r": 1.0, "g": 0.2, "b": 0.2})

    if leaf_type == "sphere" and levels >= 2:
        canopy_y = trunk_h * 0.85
        canopy_r = trunk_h * 0.4
        cv, ci = _deformed_mesh("sphere", {"x": canopy_r * 2, "y": canopy_r * 1.6, "z": canopy_r * 2},
                                displacement=0.12, detail=2, seed=seed + 7)
        for i in range(len(cv)):
            cv[i] = [cv[i][0], cv[i][1] + canopy_y, cv[i][2]]
        parts.append((cv, ci, leaf_color, "canopy"))

    # If fruits are requested, we distribute them randomly in the canopy area
    if fruit_count > 0:
        canopy_y = trunk_h * 0.85
        canopy_r = trunk_h * 0.45
        for f_idx in range(fruit_count):
            # Random position within canopy ellipsoid
            phi = _rng.uniform(0, math.pi * 2)
            theta = _rng.uniform(0, math.pi)
            dist = _rng.uniform(0.3, 1.0)
            fx = canopy_r * dist * math.sin(theta) * math.cos(phi)
            fy = canopy_y + (canopy_r * 0.7) * dist * math.cos(theta)
            fz = canopy_r * dist * math.sin(theta) * math.sin(phi)
            
            fv, fi = _sphere_mesh(fruit_size, fruit_size, fruit_size, rings=4, segs=6)
            for i in range(len(fv)):
                fv[i] = [fv[i][0] + fx, fv[i][1] + fy, fv[i][2] + fz]
            parts.append((fv, fi, fruit_color, f"fruit_{f_idx}"))

    return parts


# ── Blob mesh (metaball-like organic body) ────────────────────────────────────

def _blob_mesh(config: dict):
    """
    Create a smooth organic body shape by blending spheres.
    config keys:
      spheres: list of {x, y, z, radius} - control spheres to blend
      resolution: int (default 32, voxel resolution)
      color: dict (default gray)
    Uses trimesh implicit surface approximation.
    """
    spheres = config.get("spheres", [])
    if not spheres:
        # Default: single sphere
        spheres = [{"x": 0, "y": 0.5, "z": 0, "radius": 0.5}]
    resolution = int(config.get("resolution", 32))

    # Compute bounding box
    all_x = [float(s.get("x", 0)) + float(s.get("radius", 0.5)) for s in spheres] + \
            [float(s.get("x", 0)) - float(s.get("radius", 0.5)) for s in spheres]
    all_y = [float(s.get("y", 0)) + float(s.get("radius", 0.5)) for s in spheres] + \
            [float(s.get("y", 0)) - float(s.get("radius", 0.5)) for s in spheres]
    all_z = [float(s.get("z", 0)) + float(s.get("radius", 0.5)) for s in spheres] + \
            [float(s.get("z", 0)) - float(s.get("radius", 0.5)) for s in spheres]
    pad = 0.1
    bounds = [[min(all_x) - pad, max(all_x) + pad],
              [min(all_y) - pad, max(all_y) + pad],
              [min(all_z) - pad, max(all_z) + pad]]

    # Create SDF grid
    from trimesh.voxel import creation as vcreation
    try:
        # Try marching cubes via skimage
        from skimage import measure as sk_measure
        grid = np.zeros((resolution, resolution, resolution), dtype=np.float32)
        for ix in range(resolution):
            for iy in range(resolution):
                for iz in range(resolution):
                    wx = bounds[0][0] + (bounds[0][1] - bounds[0][0]) * ix / (resolution - 1)
                    wy = bounds[1][0] + (bounds[1][1] - bounds[1][0]) * iy / (resolution - 1)
                    wz = bounds[2][0] + (bounds[2][1] - bounds[2][0]) * iz / (resolution - 1)
                    val = 0.0
                    for s in spheres:
                        sx, sy, sz = float(s.get("x", 0)), float(s.get("y", 0)), float(s.get("z", 0))
                        sr = float(s.get("radius", 0.5))
                        dist = math.sqrt((wx - sx) ** 2 + (wy - sy) ** 2 + (wz - sz) ** 2)
                        # Metaball field function
                        val += (sr ** 3) / (dist ** 3 + 0.001)
                    grid[ix, iy, iz] = val

        # Marching cubes at threshold = 1.0
        spacing = [(bounds[a][1] - bounds[a][0]) / (resolution - 1) for a in range(3)]
        verts_mc, faces_mc, _, _ = sk_measure.marching_cubes(grid, level=1.0, spacing=spacing)
        verts_mc += np.array([bounds[0][0], bounds[1][0], bounds[2][0]])
        verts_out = np.ascontiguousarray(verts_mc, dtype=np.float32)
        indices_out = np.ascontiguousarray(faces_mc.flatten(), dtype=np.uint16)
        # Check index range
        if indices_out.max() >= len(verts_out):
            indices_out = indices_out.astype(np.uint32)
        return verts_out, indices_out
    except ImportError:
        # Fallback: simple union of spheres via trimesh
        meshes = []
        for s in spheres:
            sx, sy, sz = float(s.get("x", 0)), float(s.get("y", 0)), float(s.get("z", 0))
            sr = float(s.get("radius", 0.5))
            m = trimesh.creation.icosphere(subdivisions=2)
            m.apply_scale(sr)
            m.apply_translation([sx, sy, sz])
            meshes.append(m)
        if len(meshes) == 1:
            result = meshes[0]
        else:
            result = meshes[0]
            for m in meshes[1:]:
                try:
                    result = result.union(m)
                except Exception:
                    result = result.union(m)
        result.fix_normals()
        verts_out = np.ascontiguousarray(result.vertices, dtype=np.float32)
        indices_out = np.ascontiguousarray(result.faces.flatten(), dtype=np.uint16)
        if indices_out.max() >= len(verts_out):
            indices_out = indices_out.astype(np.uint32)
        return verts_out, indices_out


# ── Procedural texture generator ─────────────────────────────────────────────

_TEX_SIZE = 256

def _generate_texture(tex_type: str, color: dict) -> bytes:
    """Generate a 256x256 PNG texture. Returns PNG bytes."""
    r = int(min(1.0, max(0.0, float(color.get("r", 0.7)))) * 255)
    g = int(min(1.0, max(0.0, float(color.get("g", 0.7)))) * 255)
    b = int(min(1.0, max(0.0, float(color.get("b", 0.7)))) * 255)
    img = Image.new("RGB", (_TEX_SIZE, _TEX_SIZE), (r, g, b))
    draw = ImageDraw.Draw(img)

    if tex_type == "brick":
        mr, mg, mb = max(0, r - 60), max(0, g - 50), max(0, b - 40)
        brick_h, brick_w = 32, 64
        for row in range(0, _TEX_SIZE, brick_h):
            offset = (brick_w // 2) * ((row // brick_h) % 2)
            draw.line([(0, row), (_TEX_SIZE, row)], fill=(mr, mg, mb), width=2)
            for col in range(offset, _TEX_SIZE, brick_w):
                draw.line([(col, row), (col, row + brick_h)], fill=(mr, mg, mb), width=2)

    elif tex_type == "wood":
        gr, gg, gb = max(0, r - 30), max(0, g - 20), max(0, b - 15)
        for y in range(0, _TEX_SIZE, 6):
            offset = int(8 * math.sin(y * 0.05))
            draw.line([(0, y + offset), (_TEX_SIZE, y + offset)], fill=(gr, gg, gb), width=2)

    elif tex_type == "fabric":
        fr, fg, fb = max(0, r - 25), max(0, g - 20), max(0, b - 15)
        for i in range(0, _TEX_SIZE, 8):
            draw.line([(i, 0), (i, _TEX_SIZE)], fill=(fr, fg, fb), width=1)
            draw.line([(0, i), (_TEX_SIZE, i)], fill=(fr, fg, fb), width=1)

    elif tex_type == "metal_brush":
        for y in range(_TEX_SIZE):
            val = r + int((hash(y * 137) % 30) - 15)
            val = max(0, min(255, val))
            draw.line([(0, y), (_TEX_SIZE, y)], fill=(val, val, val), width=1)

    elif tex_type == "checker":
        cr, cg, cb = max(0, r - 80), max(0, g - 80), max(0, b - 80)
        cell = 32
        for row in range(0, _TEX_SIZE, cell):
            for col in range(0, _TEX_SIZE, cell):
                if ((row // cell) + (col // cell)) % 2:
                    draw.rectangle([col, row, col + cell, row + cell], fill=(cr, cg, cb))

    elif tex_type == "dragon_scale":
        sr, sg, sb = max(0, r - 40), max(0, g - 30), max(0, b - 25)
        scale_r = 20
        for row in range(0, _TEX_SIZE + scale_r, int(scale_r * 1.5)):
            offset = scale_r if (row // int(scale_r * 1.5)) % 2 else 0
            for col in range(-scale_r + offset, _TEX_SIZE + scale_r, scale_r * 2):
                draw.pieslice([col, row - scale_r, col + scale_r * 2, row + scale_r],
                              0, 180, fill=(sr, sg, sb))

    elif tex_type == "tile":
        tr, tg, tb = max(0, r - 50), max(0, g - 40), max(0, b - 35)
        tile_s = 64
        for row in range(0, _TEX_SIZE, tile_s):
            for col in range(0, _TEX_SIZE, tile_s):
                draw.rectangle([col, row, col + tile_s - 2, row + tile_s - 2], fill=(tr, tg, tb))
                draw.rectangle([col + 1, row + 1, col + tile_s - 3, row + tile_s - 3], fill=(r, g, b))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── CSG boolean operations via trimesh/manifold ─────────────────────────────

def _part_to_trimesh(part: dict) -> trimesh.Trimesh:
    """Convert a part dict to a trimesh.Trimesh for CSG operations."""
    shape = str(part.get("shape", "box")).lower()
    size = part.get("size", {})
    sx = float(size.get("x", 1.0))
    sy = float(size.get("y", 1.0))
    sz = float(size.get("z", 1.0))

    if shape == "sphere":
        m = trimesh.creation.icosphere(subdivisions=2)
        m.apply_scale([sx / 2, sy / 2, sz / 2])
    elif shape == "cylinder":
        r = (sx + sz) / 2
        m = trimesh.creation.cylinder(radius=r, height=sy, sections=24)
    elif shape == "cone":
        r = (sx + sz) / 2
        m = trimesh.creation.cone(radius=r, height=sy, sections=24)
    elif shape == "capsule":
        r = (sx + sz) / 2
        m = trimesh.creation.capsule(radius=r, height=sy)
    else:
        m = trimesh.creation.box(extents=[sx, sy, sz])

    # Apply position and rotation
    pos = part.get("position", {})
    rot = part.get("rotation", {})
    px = float(pos.get("x", 0))
    py = float(pos.get("y", 0))
    pz = float(pos.get("z", 0))
    rx = float(rot.get("x", 0))
    ry = float(rot.get("y", 0))
    rz = float(rot.get("z", 0))

    transform = trimesh.transformations.euler_matrix(
        math.radians(rx), math.radians(ry), math.radians(rz))
    transform[:3, 3] = [px, py, pz]
    m.apply_transform(transform)
    return m


def _csg_boolean(base: trimesh.Trimesh, tool: trimesh.Trimesh, operation: str) -> trimesh.Trimesh:
    """Perform CSG boolean: union, subtract, intersect."""
    if operation == "subtract":
        result = base.difference(tool)
    elif operation == "intersect":
        result = base.intersection(tool)
    else:  # union
        result = base.union(tool)
    if result is None or len(result.vertices) == 0:
        return base
    return result


# ── GLB assembly ──────────────────────────────────────────────────────────────

def _euler_to_quat(rx_deg: float, ry_deg: float, rz_deg: float) -> list:
    """XYZ intrinsic euler (degrees) → quaternion [x,y,z,w]."""
    rx = math.radians(rx_deg) / 2
    ry = math.radians(ry_deg) / 2
    rz = math.radians(rz_deg) / 2
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        sx*cy*cz + cx*sy*sz,
        cx*sy*cz - sx*cy*sz,
        cx*cy*sz + sx*sy*cz,
        cx*cy*cz - sx*sy*sz,
    ]


def build_glb(parts: list[dict]) -> bytes:
    """
    Build a GLB binary from a list of part dicts.
    Supports: box/sphere/cylinder/cone/capsule/lathe/extrude shapes,
    CSG boolean operations, procedural textures, PBR materials.
    Returns raw bytes ready to write to a .glb file.
    """
    gltf = pygltflib.GLTF2()
    gltf.scene = 0
    gltf.scenes = [pygltflib.Scene(nodes=[])]
    gltf.asset = pygltflib.Asset(version="2.0", generator="VirtualDirector-GLBBuilder")

    all_bin = bytearray()
    print(f"[GLBBuilder] Building GLB with {len(parts)} parts")

    def _add_accessor_f32(data: np.ndarray, atype: str) -> int:
        nonlocal all_bin
        raw = data.astype(np.float32).tobytes()
        bv_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(pygltflib.BufferView(
            buffer=0, byteOffset=len(all_bin), byteLength=len(raw),
            target=pygltflib.ARRAY_BUFFER,
        ))
        all_bin += raw
        ac_idx = len(gltf.accessors)
        mn = data.min(axis=0).tolist() if data.ndim > 1 else [float(data.min())]
        mx = data.max(axis=0).tolist() if data.ndim > 1 else [float(data.max())]
        gltf.accessors.append(pygltflib.Accessor(
            bufferView=bv_idx, componentType=pygltflib.FLOAT,
            count=len(data), type=atype,
            min=mn, max=mx,
        ))
        return ac_idx

    def _add_accessor_u16(data: np.ndarray) -> int:
        nonlocal all_bin
        raw = data.astype(np.uint16).tobytes()
        bv_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(pygltflib.BufferView(
            buffer=0, byteOffset=len(all_bin), byteLength=len(raw),
            target=pygltflib.ELEMENT_ARRAY_BUFFER,
        ))
        all_bin += raw
        ac_idx = len(gltf.accessors)
        gltf.accessors.append(pygltflib.Accessor(
            bufferView=bv_idx, componentType=pygltflib.UNSIGNED_SHORT,
            count=len(data), type=pygltflib.SCALAR,
            min=[int(data.min())], max=[int(data.max())],
        ))
        return ac_idx

    def _add_image(png_bytes: bytes) -> int:
        """Add a PNG image to the glTF, return image index."""
        nonlocal all_bin
        img_idx = len(gltf.images)
        bv_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(pygltflib.BufferView(
            buffer=0, byteOffset=len(all_bin), byteLength=len(png_bytes),
        ))
        all_bin += png_bytes
        gltf.images.append(pygltflib.Image(
            bufferView=bv_idx, mimeType="image/png",
        ))
        return img_idx

    def _generate_uvs_box(sx, sy, sz, n_verts=24):
        """Generate UV coords for a box mesh (6 faces × 4 verts)."""
        uvs = []
        # front/back: map XZ
        for _ in range(8):
            pass
        # Simplified: each face gets 0-1 UV
        for face in range(6):
            uvs += [[0,0],[1,0],[1,1],[0,1]]
        return np.array(uvs[:n_verts], dtype=np.float32)

    def _generate_uvs_sphere(n_rings, n_segs):
        """Generate UV coords for sphere mesh."""
        uvs = []
        for i in range(n_rings + 1):
            v = i / n_rings
            for j in range(n_segs):
                u = j / n_segs
                uvs.append([u, v])
        return np.array(uvs, dtype=np.float32)

    def _generate_uvs_cylinder(n_segs):
        """Generate UV coords for cylinder mesh (simplified)."""
        # Side verts (top+bot), cap center, cap ring × 2
        n_side = n_segs * 2
        n_cap = n_segs + 1
        uvs = []
        # Side
        for i in range(n_segs):
            u = i / n_segs
            uvs += [[u, 1], [u, 0]]
        # Top cap center
        uvs += [[0.5, 0.5]]
        # Top cap ring
        for i in range(n_segs):
            a = 2 * math.pi * i / n_segs
            uvs += [[0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)]]
        # Bot cap center
        uvs += [[0.5, 0.5]]
        # Bot cap ring
        for i in range(n_segs):
            a = 2 * math.pi * i / n_segs
            uvs += [[0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)]]
        return np.array(uvs, dtype=np.float32)

    for part in parts:
        shape    = str(part.get("shape", "box")).lower()
        size     = part.get("size", {})
        pos      = part.get("position", {})
        rot      = part.get("rotation", {})
        color    = part.get("color", {"r": 0.7, "g": 0.7, "b": 0.7})
        name     = str(part.get("name", "part"))
        tex_type = part.get("texture", None)

        sx = float(size.get("x", 1.0))
        sy = float(size.get("y", 1.0))
        sz = float(size.get("z", 1.0))

        # ── CSG boolean operation ──────────────────────────────────────────
        csg_spec = part.get("csg", None)
        if csg_spec:
            try:
                base_mesh = _part_to_trimesh(part)
                tool_mesh = _part_to_trimesh(csg_spec.get("tool", {}))
                operation = csg_spec.get("operation", "subtract")
                result_mesh = _csg_boolean(base_mesh, tool_mesh, operation)
                verts = np.ascontiguousarray(result_mesh.vertices, dtype=np.float32)
                indices = np.ascontiguousarray(result_mesh.faces.flatten(), dtype=np.uint16)
                # CSG result is already in world space, reset position/rotation
                pos = {"x": 0, "y": 0, "z": 0}
                rot = {"x": 0, "y": 0, "z": 0}
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[GLBBuilder] CSG failed for {name}: {e}, falling back to base shape")
                if shape == "sphere":
                    verts, indices = _sphere_mesh(sx/2, sy/2, sz/2)
                elif shape == "cylinder":
                    verts, indices = _cylinder_mesh(sx, sy, sz)
                elif shape == "cone":
                    verts, indices = _cone_mesh(sx, sy, sz)
                elif shape == "capsule":
                    verts, indices = _capsule_mesh(sx, sy, sz)
                else:
                    verts, indices = _box_mesh(sx, sy, sz)
        elif shape == "lathe":
            profile = part.get("profile", [])
            verts, indices = _lathe_mesh(profile)
        elif shape == "extrude":
            cross_section = part.get("cross_section", [])
            depth = float(part.get("extrude_depth", 0.5))
            verts, indices = _extrude_mesh(cross_section, depth)
        elif shape == "spline_tube":
            spline_points = part.get("points", [])
            if len(spline_points) < 2:
                print(f"[GLBBuilder] spline_tube {name} has < 2 points, falling back to sphere")
                verts, indices = _sphere_mesh(sx/2, sy/2, sz/2)
            else:
                spline_radius = float(part.get("radius", 0.05))
                spline_segs = int(part.get("segments", 8))
                spline_interp = int(part.get("interp_steps", 24))
                verts, indices = _spline_tube_mesh(spline_points, spline_radius, spline_segs, spline_interp)
                pos = {"x": 0, "y": 0, "z": 0}
                rot = {"x": 0, "y": 0, "z": 0}
        elif shape == "deformed":
            disp = float(part.get("displacement", 0.15))
            detail = int(part.get("detail", 2))
            seed = int(part.get("seed", 42))
            spikes = float(part.get("spikes", 0.0))
            verts, indices = _deformed_mesh("sphere", size, disp, detail, seed, spikes)
            pos = {"x": 0, "y": 0, "z": 0}
            rot = {"x": 0, "y": 0, "z": 0}
        elif shape == "blob":
            blob_config = part.get("blob_config", {})
            verts, indices = _blob_mesh(blob_config)
            pos = {"x": 0, "y": 0, "z": 0}
            rot = {"x": 0, "y": 0, "z": 0}
        elif shape == "tree":
            tree_config = part.get("tree_config", {})
            tree_parts = _tree_mesh(tree_config)
            # Tree generates multiple sub-parts; we add them all as separate meshes
            for tp_idx, (tv, ti, tc, tn) in enumerate(tree_parts):
                tp_pos_acc = _add_accessor_f32(tv, pygltflib.VEC3)
                tp_idx_acc = _add_accessor_u16(ti)
                tp_mat_idx = len(gltf.materials)
                tr = min(1.0, max(0.0, float(tc.get("r", 0.7))))
                tg = min(1.0, max(0.0, float(tc.get("g", 0.7))))
                tb = min(1.0, max(0.0, float(tc.get("b", 0.7))))
                gltf.materials.append(pygltflib.Material(
                    name=f"{name}_{tn}_mat",
                    pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                        baseColorFactor=[tr, tg, tb, 1.0],
                        metallicFactor=float(part.get("metallic", 0.0)),
                        roughnessFactor=float(part.get("roughness", 0.9)),
                    ),
                    doubleSided=True,
                ))
                tp_mesh_idx = len(gltf.meshes)
                gltf.meshes.append(pygltflib.Mesh(
                    name=f"{name}_{tn}",
                    primitives=[pygltflib.Primitive(
                        attributes=pygltflib.Attributes(POSITION=tp_pos_acc),
                        indices=tp_idx_acc,
                        material=tp_mat_idx,
                    )],
                ))
                tp_node_idx = len(gltf.nodes)
                gltf.nodes.append(pygltflib.Node(
                    name=f"{name}_{tn}",
                    mesh=tp_mesh_idx,
                    translation=[0, 0, 0],
                ))
                gltf.scenes[0].nodes.append(tp_node_idx)
            continue  # skip the normal single-part processing below
        elif shape == "sphere":
            verts, indices = _sphere_mesh(sx/2, sy/2, sz/2)
        elif shape == "cylinder":
            verts, indices = _cylinder_mesh(sx, sy, sz)
        elif shape == "cone":
            verts, indices = _cone_mesh(sx, sy, sz)
        elif shape == "capsule":
            verts, indices = _capsule_mesh(sx, sy, sz)
        else:
            if shape != "box":
                print(f"[GLBBuilder] Unknown shape '{shape}', defaulting to box")
            verts, indices = _box_mesh(sx, sy, sz)

        pos_acc = _add_accessor_f32(verts, pygltflib.VEC3)
        idx_acc = _add_accessor_u16(indices)

        # ── Texture handling ───────────────────────────────────────────────
        tex_coord_acc = None
        tex_idx = None
        if tex_type:
            try:
                png_bytes = _generate_texture(tex_type, color)
                img_idx = _add_image(png_bytes)
                tex_idx = len(gltf.textures)
                gltf.textures.append(pygltflib.Texture(source=img_idx))

                # Generate UV coords based on shape
                if shape == "sphere":
                    uv_data = _generate_uvs_sphere(12, 16)
                elif shape == "cylinder":
                    uv_data = _generate_uvs_cylinder(16)
                elif shape == "lathe":
                    # Lathe UVs: u = theta segment, v = profile height
                    profile = part.get("profile", [])
                    n_pts = max(len(profile), 2)
                    segs = 24
                    uv_data = []
                    for i in range(n_pts):
                        v = i / max(n_pts - 1, 1)
                        for j in range(segs):
                            u = j / segs
                            uv_data.append([u, v])
                    uv_data = np.array(uv_data, dtype=np.float32)
                else:
                    # Box/cone/capsule/extrude: simple planar projection
                    # Normalize verts to 0-1 range for UV
                    vmin = verts.min(axis=0)
                    vmax = verts.max(axis=0)
                    vrange = vmax - vmin
                    vrange[vrange == 0] = 1.0
                    uv_data = (verts - vmin) / vrange
                    # Use XZ for U, Y for V
                    uv_data = np.stack([uv_data[:, 0], uv_data[:, 1]], axis=1).astype(np.float32)

                # Ensure UV count matches vertex count
                if len(uv_data) < len(verts):
                    uv_data = np.pad(uv_data, ((0, len(verts) - len(uv_data)), (0, 0)), mode='edge')
                elif len(uv_data) > len(verts):
                    uv_data = uv_data[:len(verts)]

                tex_coord_acc = _add_accessor_f32(uv_data, pygltflib.VEC2)
            except Exception as e:
                print(f"[GLBBuilder] Texture failed for {name}: {e}")

        # ── Material ───────────────────────────────────────────────────────
        mat_idx = len(gltf.materials)
        r = min(1.0, max(0.0, float(color.get("r", 0.7))))
        g = min(1.0, max(0.0, float(color.get("g", 0.7))))
        b = min(1.0, max(0.0, float(color.get("b", 0.7))))
        a = min(1.0, max(0.0, float(color.get("a", 1.0))))
        metallic  = min(1.0, max(0.0, float(part.get("metallic", 0.1))))
        roughness = min(1.0, max(0.0, float(part.get("roughness", 0.8))))
        emissive  = part.get("emissive", None)
        alpha_mode = pygltflib.BLEND if a < 0.99 else pygltflib.OPAQUE
        pbr = pygltflib.PbrMetallicRoughness(
            baseColorFactor=[r, g, b, a],
            metallicFactor=metallic,
            roughnessFactor=roughness,
        )
        if tex_idx is not None:
            pbr.baseColorTexture = pygltflib.TextureInfo(index=tex_idx)
        mat_kwargs = dict(
            name=name + "_mat",
            pbrMetallicRoughness=pbr,
            doubleSided=True,
            alphaMode=alpha_mode,
        )
        if emissive:
            er = min(1.0, max(0.0, float(emissive.get("r", 0.0))))
            eg = min(1.0, max(0.0, float(emissive.get("g", 0.0))))
            eb = min(1.0, max(0.0, float(emissive.get("b", 0.0))))
            ei = min(5.0, max(0.0, float(emissive.get("intensity", 1.0))))
            mat_kwargs["emissiveFactor"] = [er * ei, eg * ei, eb * ei]
            if tex_idx is not None:
                mat_kwargs["emissiveTexture"] = pygltflib.TextureInfo(index=tex_idx)
        gltf.materials.append(pygltflib.Material(**mat_kwargs))

        # ── Mesh + Node ────────────────────────────────────────────────────
        mesh_idx = len(gltf.meshes)
        prim_attrs = pygltflib.Attributes(POSITION=pos_acc)
        if tex_coord_acc is not None:
            prim_attrs.TEXCOORD_0 = tex_coord_acc
        gltf.meshes.append(pygltflib.Mesh(
            name=name,
            primitives=[pygltflib.Primitive(
                attributes=prim_attrs,
                indices=idx_acc,
                material=mat_idx,
            )],
        ))

        px = float(pos.get("x", 0.0))
        py = float(pos.get("y", 0.0))
        pz = float(pos.get("z", 0.0))
        rx = float(rot.get("x", 0.0))
        ry = float(rot.get("y", 0.0))
        rz = float(rot.get("z", 0.0))
        quat = _euler_to_quat(rx, ry, rz)

        scale = part.get("scale", None)
        node_kwargs = dict(
            name=name,
            mesh=mesh_idx,
            translation=[px, py, pz],
            rotation=quat,
        )
        if scale:
            node_kwargs["scale"] = [
                float(scale.get("x", 1.0)),
                float(scale.get("y", 1.0)),
                float(scale.get("z", 1.0)),
            ]

        node_idx = len(gltf.nodes)
        gltf.nodes.append(pygltflib.Node(**node_kwargs))
        gltf.scenes[0].nodes.append(node_idx)

    gltf.buffers = [pygltflib.Buffer(byteLength=len(all_bin))]
    gltf.set_binary_blob(bytes(all_bin))

    tmp_bytes = b"".join(gltf.save_to_bytes())
    return tmp_bytes
