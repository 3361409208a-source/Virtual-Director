import json
import os
import re

from backend.config import GODOT_DIR, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

CUSTOM_DIR = os.path.join(GODOT_DIR, "assets", "custom")

_VOXEL_SYSTEM = """你是一个我的世界（Minecraft）风格的 3D 像素艺术家，擅长结合动态特效进行建模。
用户描述一个物体，你用体素方块（voxels）来描述它的 3D 结构，并标记出其中的动态特效区域。

严格输出以下 JSON 格式，不要输出任何其他文字：
{
  "name": "物体名称",
  "vfx_hint": "特效类型建议 (如: fire, lightning, magic_aura, laser_beam, water_flow, smoke, none)",
  "blocks": [
    {"x": 0, "y": 0, "z": 0, "r": 180, "g": 80, "b": 50, "fx": "none"},
    ...
  ]
}

规则：
- 坐标范围：x/z 在 0-15，y 在 0-12
- 颜色 r/g/b 各 0-255
- fx 字段可选值："none" (普通方块), "glow" (发光方块), "animated" (动态核心)
- 控制在 80-250 个方块
- 如果用户提到特效（如“发光的宝剑”、“喷火的龙”），请务必在对应位置标记 fx: "glow" 或 "animated"。
"""


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name).strip("_") or "voxel_model"


def _call_llm_for_voxels(prompt: str, model: str = "deepseek-chat") -> dict:
    from openai import OpenAI
    from backend.services.llm import _get_client_config

    client, model_name = _get_client_config(model)
    if client is None:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60.0)
        model_name = "deepseek-chat"

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _VOXEL_SYSTEM},
            {"role": "user", "content": f"请为以下物体设计带有动态潜力的 3D 体素结构：{prompt}"},
        ],
        temperature=0.7,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    content = (resp.choices[0].message.content or "{}").strip()
    content = re.sub(r"```json\s*|\s*```", "", content).strip()
    data = json.loads(content)
    return data


def _blocks_to_glb(blocks: list, dest: str) -> None:
    import trimesh
    import numpy as np

    if not blocks:
        raise ValueError("LLM 未返回任何方块数据")

    meshes = []
    for b in blocks:
        try:
            x, y, z = float(b["x"]), float(b["y"]), float(b["z"])
            r = max(0, min(255, int(b.get("r", 128))))
            g = max(0, min(255, int(b.get("g", 128))))
            bl = max(0, min(255, int(b.get("b", 128))))
            
            # If the block is "glow", we make it slightly emissive in vertex colors (alpha trick or separate list)
            # For simplicity in GLB export via trimesh, we'll keep them in one mesh but we could separate them
            box = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
            box.apply_translation([x + 0.5, y + 0.5, z + 0.5])
            
            # Special fx handling: we can encode FX info in the alpha channel or a separate metadata
            alpha = 255
            if b.get("fx") == "glow":
                alpha = 254 # Custom tag for renderer
            elif b.get("fx") == "animated":
                alpha = 253
                
            box.visual.vertex_colors = [r, g, bl, alpha]
            meshes.append(box)
        except (KeyError, ValueError, TypeError):
            continue

    if not meshes:
        raise ValueError("所有方块数据解析失败")

    combined = trimesh.util.concatenate(meshes)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    combined.export(dest, file_type="glb")


def generate_voxel_asset(
    prompt: str,
    model_name: str = "voxel_model",
    llm_model: str = "deepseek-chat",
    progress_cb=None,
) -> dict:
    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)

    _log("🟫 [Minecraft] AI 正在设计带特效的体素结构...")
    data = _call_llm_for_voxels(prompt, llm_model)
    blocks = data.get("blocks", [])
    vfx_hint = data.get("vfx_hint", "none")
    
    _log(f"🟫 [Minecraft] 已规划 {len(blocks)} 个方块，包含特效标签: {vfx_hint}...")

    os.makedirs(CUSTOM_DIR, exist_ok=True)
    filename = f"{_safe_name(model_name)}.glb"
    dest = os.path.join(CUSTOM_DIR, filename)

    _blocks_to_glb(blocks, dest)

    size_kb = os.path.getsize(dest) // 1024
    _log(f"✅ [Minecraft] 体素模型完成：{filename}（包含动态特效元数据）")

    return {
        "filename": filename,
        "path": dest,
        "url": f"/api/models/custom/{filename}",
        "size_kb": size_kb,
        "blocks_count": len(blocks),
        "vfx_hint": vfx_hint,
    }
