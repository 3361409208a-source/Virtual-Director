"""
Convert a composite asset manifest (list of primitive parts) into
a binary GLB file using pygltflib.

Each part schema:
{
  "name": "torso",
  "shape": "box" | "sphere" | "cylinder" | "cone" | "capsule",
  "size":     {"x": 0.5, "y": 0.9, "z": 0.3},   # bounding box extents
  "position": {"x": 0.0, "y": 0.5, "z": 0.0},
  "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},   # euler degrees, optional
  "color":    {"r": 0.8, "g": 0.2, "b": 0.2, "a": 1.0},  # 0-1 float RGBA, a optional
  "metallic":  0.1,      # 0-1, default 0.1 (0=non-metal, 1=full metal)
  "roughness": 0.8,      # 0-1, default 0.8 (0=mirror, 1=matte)
  "emissive":  {"r": 0, "g": 1, "b": 0, "intensity": 2.0},  # optional self-illumination
  "scale":     {"x": 1.0, "y": 1.0, "z": 1.0},   # optional non-uniform scale
}
"""

import math
import struct
import numpy as np
import pygltflib


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

    for part in parts:
        shape    = str(part.get("shape", "box")).lower()
        size     = part.get("size", {})
        pos      = part.get("position", {})
        rot      = part.get("rotation", {})
        color    = part.get("color", {"r": 0.7, "g": 0.7, "b": 0.7})
        name     = str(part.get("name", "part"))

        sx = float(size.get("x", 1.0))
        sy = float(size.get("y", 1.0))
        sz = float(size.get("z", 1.0))

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

        pos_acc = _add_accessor_f32(verts, pygltflib.VEC3)
        idx_acc = _add_accessor_u16(indices)

        mat_idx = len(gltf.materials)
        r = min(1.0, max(0.0, float(color.get("r", 0.7))))
        g = min(1.0, max(0.0, float(color.get("g", 0.7))))
        b = min(1.0, max(0.0, float(color.get("b", 0.7))))
        a = min(1.0, max(0.0, float(color.get("a", 1.0))))
        metallic  = min(1.0, max(0.0, float(part.get("metallic", 0.1))))
        roughness = min(1.0, max(0.0, float(part.get("roughness", 0.8))))
        emissive  = part.get("emissive", None)
        alpha_mode = pygltflib.BLEND if a < 0.99 else pygltflib.OPAQUE
        mat_kwargs = dict(
            name=name + "_mat",
            pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                baseColorFactor=[r, g, b, a],
                metallicFactor=metallic,
                roughnessFactor=roughness,
            ),
            doubleSided=True,
            alphaMode=alpha_mode,
        )
        if emissive:
            er = min(1.0, max(0.0, float(emissive.get("r", 0.0))))
            eg = min(1.0, max(0.0, float(emissive.get("g", 0.0))))
            eb = min(1.0, max(0.0, float(emissive.get("b", 0.0))))
            ei = min(5.0, max(0.0, float(emissive.get("intensity", 1.0))))
            mat_kwargs["emissiveFactor"] = [er * ei, eg * ei, eb * ei]
        gltf.materials.append(pygltflib.Material(**mat_kwargs))

        mesh_idx = len(gltf.meshes)
        gltf.meshes.append(pygltflib.Mesh(
            name=name,
            primitives=[pygltflib.Primitive(
                attributes=pygltflib.Attributes(POSITION=pos_acc),
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

    import io
    buf = io.BytesIO()
    # Serialize to temporary file path trick: use convert to binary in-memory
    tmp_bytes = b"".join(gltf.save_to_bytes())
    return tmp_bytes
