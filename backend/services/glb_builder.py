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


def _cone_mesh(rx: float, ry: float, rz: float, segs: int = 16):
    """Cone along Y axis, base radius=(rx+rz)/2, height=ry, tip at top."""
    r = (rx + rz) / 2
    h = ry / 2
    verts = []
    idx = []
    # Base ring + center
    for i in range(segs):
        a = 2 * math.pi * i / segs
        verts.append([r * math.cos(a), -h, r * math.sin(a)])
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


def _capsule_mesh(rx: float, ry: float, rz: float, rings: int = 8, segs: int = 16):
    """Capsule along Y axis: cylinder body + hemisphere caps. radius=(rx+rz)/2, total height=ry."""
    r = (rx + rz) / 2
    h = ry / 2  # total half-height
    cap_h = min(r, h)  # cap height cannot exceed half of total
    body_h = h - cap_h  # cylinder body half-height
    verts = []
    idx = []
    # Bottom hemisphere
    for i in range(rings + 1):
        phi = math.pi * i / (2 * rings)  # 0 to pi/2 (bottom cap inverted)
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([
                r * math.sin(phi) * math.cos(theta),
                -(body_h + r * math.cos(phi)),
                r * math.sin(phi) * math.sin(theta),
            ])
    # Top hemisphere
    for i in range(rings + 1):
        phi = math.pi * i / (2 * rings)  # 0 to pi/2
        for j in range(segs):
            theta = 2 * math.pi * j / segs
            verts.append([
                r * math.sin(phi) * math.cos(theta),
                body_h + r * math.cos(phi),
                r * math.sin(phi) * math.sin(theta),
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


def _cylinder_mesh(rx: float, ry: float, rz: float, segs: int = 16):
    """Capped cylinder along Y axis, radius=(rx+rz)/2, half-height=ry/2."""
    r = (rx + rz) / 2
    h = ry / 2
    top_verts, bot_verts, side_top, side_bot = [], [], [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        x, z = r * math.cos(a), r * math.sin(a)
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
        elif shape == "sphere":
            verts, indices = _sphere_mesh(sx/2, sy/2, sz/2)
        elif shape == "cylinder":
            verts, indices = _cylinder_mesh(sx, sy, sz)
        elif shape == "cone":
            verts, indices = _cone_mesh(sx, sy, sz)
        elif shape == "capsule":
            verts, indices = _capsule_mesh(sx, sy, sz)
        else:
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
