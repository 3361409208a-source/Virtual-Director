"""
Skeleton Rigger — 自动骨骼识别与蒙皮绑定

算法：
1. 加载 GLB，读取所有网格节点的世界空间位置
2. 根据节点名称判断模型类型（人形 / 通用）
3. 按比例生成骨骼层级（人形: 18骨 / 通用: 5骨）
4. 为每个网格顶点绑定最近的骨骼（单骨权重=1.0）
5. 写入 JOINTS_0 / WEIGHTS_0 属性和 inverseBindMatrices
6. 输出含骨骼的新 GLB
"""

import math
import struct
import numpy as np
import pygltflib

# ─────────────────────────────────────────────────────────────────────────────
# 骨骼模板定义  (name, parent_name, y_rel [0-1], x_offset_rel, z_offset_rel)
# x/z_offset_rel 以模型总宽度为单位
# ─────────────────────────────────────────────────────────────────────────────

_HUMANOID_BONES = [
    ("root",              None,                 0.00,  0.00,  0.00),
    ("hips",              "root",               0.47,  0.00,  0.00),
    ("spine",             "hips",               0.56,  0.00,  0.00),
    ("chest",             "spine",              0.64,  0.00,  0.00),
    ("neck",              "chest",              0.74,  0.00,  0.00),
    ("head",              "neck",               0.86,  0.00,  0.00),
    ("left_upper_arm",    "chest",              0.66, -0.20,  0.00),
    ("left_lower_arm",    "left_upper_arm",     0.55, -0.28,  0.00),
    ("left_hand",         "left_lower_arm",     0.45, -0.34,  0.00),
    ("right_upper_arm",   "chest",              0.66,  0.20,  0.00),
    ("right_lower_arm",   "right_upper_arm",    0.55,  0.28,  0.00),
    ("right_hand",        "right_lower_arm",    0.45,  0.34,  0.00),
    ("left_upper_leg",    "hips",               0.37, -0.11,  0.00),
    ("left_lower_leg",    "left_upper_leg",     0.20, -0.11,  0.00),
    ("left_foot",         "left_lower_leg",     0.03, -0.11,  0.06),
    ("right_upper_leg",   "hips",               0.37,  0.11,  0.00),
    ("right_lower_leg",   "right_upper_leg",    0.20,  0.11,  0.00),
    ("right_foot",        "right_lower_leg",    0.03,  0.11,  0.06),
]

_GENERIC_BONES = [
    ("root",   None,     0.00, 0.00, 0.00),
    ("lower",  "root",   0.22, 0.00, 0.00),
    ("middle", "lower",  0.50, 0.00, 0.00),
    ("upper",  "middle", 0.75, 0.00, 0.00),
    ("top",    "upper",  0.95, 0.00, 0.00),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_body_type(gltf: pygltflib.GLTF2) -> str:
    names = [(n.name or "").lower() for n in gltf.nodes if n.mesh is not None]
    kw = ["head", "torso", "body", "arm", "leg", "hand", "foot",
          "neck", "spine", "chest", "hip", "shoulder", "knee", "elbow"]
    score = sum(1 for name in names for k in kw if k in name)
    return "humanoid" if score >= 2 else "generic"


def _model_bounds(gltf: pygltflib.GLTF2):
    """Return (ymin, ymax, xmin, xmax) of all mesh nodes."""
    ymin = xmin = float("inf")
    ymax = xmax = float("-inf")
    for node in gltf.nodes:
        if node.mesh is None:
            continue
        tx, ty, _ = (node.translation or [0.0, 0.0, 0.0])
        mesh = gltf.meshes[node.mesh]
        for prim in mesh.primitives:
            if prim.attributes is None or prim.attributes.POSITION is None:
                continue
            acc = gltf.accessors[prim.attributes.POSITION]
            if acc.min and acc.max:
                ymin = min(ymin, acc.min[1] + ty)
                ymax = max(ymax, acc.max[1] + ty)
                xmin = min(xmin, acc.min[0] + tx)
                xmax = max(xmax, acc.max[0] + tx)
    if math.isinf(ymin):
        ymin, ymax, xmin, xmax = 0.0, 1.8, -0.3, 0.3
    return ymin, ymax, xmin, xmax


def _classify_node(node_y: float, node_name: str,
                   ymin: float, ymax: float, bone_defs: list) -> int:
    """Return the best-matching bone index for a mesh node."""
    name_l = (node_name or "").lower()
    yrel = (node_y - ymin) / max(0.001, ymax - ymin)

    # Name-based match first
    for i, (bname, *_) in enumerate(bone_defs):
        clean = bname.replace("_", " ")
        if bname in name_l or clean in name_l:
            return i

    # Fallback: nearest by Y proportion
    best, best_d = 0, float("inf")
    for i, (_, _, ypos, _, _) in enumerate(bone_defs):
        d = abs(ypos - yrel)
        if d < best_d:
            best_d = d
            best = i
    return best


def _append_buffer(binary: bytearray, data: bytes,
                   gltf: pygltflib.GLTF2) -> int:
    """Append data to binary blob, add BufferView, return BufferView index."""
    offset = len(binary)
    binary.extend(data)
    while len(binary) % 4:
        binary.append(0)
    bv_idx = len(gltf.bufferViews)
    gltf.bufferViews.append(pygltflib.BufferView(
        buffer=0,
        byteOffset=offset,
        byteLength=len(data),
    ))
    return bv_idx


def _add_accessor(gltf: pygltflib.GLTF2, bv_idx: int,
                  component_type: int, acc_type: str, count: int) -> int:
    acc_idx = len(gltf.accessors)
    gltf.accessors.append(pygltflib.Accessor(
        bufferView=bv_idx,
        byteOffset=0,
        componentType=component_type,
        type=acc_type,
        count=count,
    ))
    return acc_idx


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def add_skeleton(src_path: str, dst_path: str) -> dict:
    """
    Load GLB from src_path, inject auto-generated skeleton + skin weights,
    save to dst_path.  Returns summary dict.
    """
    gltf = pygltflib.GLTF2().load(src_path)
    binary = bytearray(gltf.binary_blob() or b"")

    body_type = _detect_body_type(gltf)
    bone_defs = _HUMANOID_BONES if body_type == "humanoid" else _GENERIC_BONES

    ymin, ymax, xmin, xmax = _model_bounds(gltf)
    height = max(0.01, ymax - ymin)
    width  = max(0.01, xmax - xmin)
    cx     = (xmin + xmax) / 2.0

    # ── 1. Compute world positions for each bone ──────────────────────────────
    bone_world: list[tuple[float, float, float]] = []
    for _, _, yrel, xoff, zoff in bone_defs:
        bone_world.append((
            cx + xoff * width,
            ymin + yrel * height,
            zoff * width,
        ))

    # ── 2. Create bone nodes ──────────────────────────────────────────────────
    first_bone_node = len(gltf.nodes)
    bone_name_to_def = {bname: i for i, (bname, *_) in enumerate(bone_defs)}

    for i, (bname, bparent, _, _, _) in enumerate(bone_defs):
        wx, wy, wz = bone_world[i]
        # Store world coords temporarily; we'll convert to local below
        gltf.nodes.append(pygltflib.Node(
            name=f"Bone_{bname}",
            translation=[wx, wy, wz],
            children=[],
        ))

    # ── 3. Wire parent-child, convert to local translations ──────────────────
    root_bone_gltf_idx = None
    for i, (bname, bparent, _, _, _) in enumerate(bone_defs):
        gltf_idx = first_bone_node + i
        if bparent is None:
            root_bone_gltf_idx = gltf_idx
        else:
            parent_def_idx = bone_name_to_def[bparent]
            parent_gltf_idx = first_bone_node + parent_def_idx
            parent_node = gltf.nodes[parent_gltf_idx]
            if parent_node.children is None:
                parent_node.children = []
            parent_node.children.append(gltf_idx)

            # Convert to local (parent-relative) translation
            pwx, pwy, pwz = bone_world[parent_def_idx]
            wx, wy, wz = bone_world[i]
            gltf.nodes[gltf_idx].translation = [wx - pwx, wy - pwy, wz - pwz]

    if root_bone_gltf_idx is not None:
        gltf.scenes[0].nodes.append(root_bone_gltf_idx)

    # ── 4. Inverse Bind Matrices (column-major 4x4 inverse-translation) ───────
    ibm_bytes = b""
    for wx, wy, wz in bone_world:
        mat = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            -wx, -wy, -wz, 1.0,
        )
        ibm_bytes += struct.pack("16f", *mat)

    ibm_bv  = _append_buffer(binary, ibm_bytes, gltf)
    ibm_acc = _add_accessor(gltf, ibm_bv, pygltflib.FLOAT, pygltflib.MAT4, len(bone_defs))

    # ── 5. Create Skin ────────────────────────────────────────────────────────
    if gltf.skins is None:
        gltf.skins = []
    skin_idx = len(gltf.skins)
    gltf.skins.append(pygltflib.Skin(
        name="AutoSkin",
        joints=[first_bone_node + i for i in range(len(bone_defs))],
        inverseBindMatrices=ibm_acc,
        skeleton=root_bone_gltf_idx,
    ))

    # ── 6. Add JOINTS_0 + WEIGHTS_0 to every mesh primitive ──────────────────
    rigged_meshes = 0
    for node in gltf.nodes[:first_bone_node]:  # only original mesh nodes
        if node.mesh is None:
            continue

        # ── Bake node transform into vertices ────────────────────────────────
        # When a node has a skin, its T/R/S are ignored by many engines.
        # We must bake the translation into the actual vertex positions.
        tx, ty, tz = (node.translation or [0.0, 0.0, 0.0])
        node.translation = [0.0, 0.0, 0.0]  # Reset node transform
        
        # Determine node world center Y for bone classification
        center_y = ty
        mesh = gltf.meshes[node.mesh]
        
        for prim in mesh.primitives:
            if prim.attributes is None or prim.attributes.POSITION is None:
                continue
            
            # 1. Get position accessor and data
            pos_acc = gltf.accessors[prim.attributes.POSITION]
            pos_bv = gltf.bufferViews[pos_acc.bufferView]
            
            # Read and update vertices in the binary blob
            start = pos_bv.byteOffset + pos_acc.byteOffset
            count = pos_acc.count
            
            # Update center_y calculation before baking
            if pos_acc.min and pos_acc.max:
                center_y = (pos_acc.min[1] + pos_acc.max[1]) / 2.0 + ty

            # Bake translation into the binary blob
            for i in range(count):
                v_offset = start + i * 12 # 3 * float32
                vx, vy, vz = struct.unpack_from("3f", binary, v_offset)
                struct.pack_into("3f", binary, v_offset, vx + tx, vy + ty, vz + tz)
            
            # Update accessor min/max after baking
            if pos_acc.min:
                pos_acc.min = [pos_acc.min[0] + tx, pos_acc.min[1] + ty, pos_acc.min[2] + tz]
            if pos_acc.max:
                pos_acc.max = [pos_acc.max[0] + tx, pos_acc.max[1] + ty, pos_acc.max[2] + tz]

            # 2. Add skinning data (JOINTS_0, WEIGHTS_0)
            n_verts = count
            bone_def_idx = _classify_node(center_y, node.name or "", ymin, ymax, bone_defs)

            # JOINTS_0  (VEC4 UNSIGNED_SHORT)
            j_arr = np.zeros((n_verts, 4), dtype=np.uint16)
            j_arr[:, 0] = bone_def_idx
            j_bv  = _append_buffer(binary, j_arr.tobytes(), gltf)
            j_acc = _add_accessor(gltf, j_bv, pygltflib.UNSIGNED_SHORT, pygltflib.VEC4, n_verts)

            # WEIGHTS_0  (VEC4 FLOAT)
            w_arr = np.zeros((n_verts, 4), dtype=np.float32)
            w_arr[:, 0] = 1.0
            w_bv  = _append_buffer(binary, w_arr.tobytes(), gltf)
            w_acc = _add_accessor(gltf, w_bv, pygltflib.FLOAT, pygltflib.VEC4, n_verts)

            prim.attributes.JOINTS_0  = j_acc
            prim.attributes.WEIGHTS_0 = w_acc

        node.skin = skin_idx
        rigged_meshes += 1

    # ── 7. Update buffer and save ─────────────────────────────────────────────
    gltf.buffers[0].byteLength = len(binary)
    gltf.set_binary_blob(bytes(binary))
    gltf.save(dst_path)

    return {
        "body_type":    body_type,
        "bones":        len(bone_defs),
        "mesh_nodes":   rigged_meshes,
        "size_kb":      len(binary) // 1024,
    }
