import os
import re
import json
import asyncio
from backend.services.llm import llm_call, set_model
from backend.tools.definitions import ai_model_tool
from backend.services.glb_builder import build_glb
from backend.config import GODOT_DIR

CUSTOM_DIR = os.path.join(GODOT_DIR, "assets", "custom")

def get_system_prompt(base_model: str = "") -> str:
    base_ctx = ""
    if base_model:
        base_ctx = f"\n参考模型名称：{base_model}（以此为灵感来源，但须按用户描述重新设计）\n"

    return (
        "你是顶尖 3D 建模技术总监，擅长通过‘几何体分解法’将复杂物体拆解为大量精细零件。\n"
        "\n═══ [极致细节指令 - 必须遵守] ═══\n"
        "1. 【拒绝敷衍】：严禁仅使用 1-3 个零件来代表复杂物体！例如：一辆汽车必须由车身、底盘、四个轮子、前后灯、车窗、后视镜等至少 15 个零件组成。\n"
        "2. 【零件数量】：纯几何体拼装建议 20-40 个零件；有机形状混合建议 12-25 个零件。\n"
        "3. 【比例精准】：严格遵守真实世界比例（人 1.8m，车 4.5m）。\n"
        "4. 【参数完整】：每个零件必须完整包含 name, shape, size{x,y,z}, position{x,y,z}, rotation{x,y,z}, color{r,g,b} 字段，缺失字段会导致渲染失败。\n"
        "\n═══ 可用形状库 ═══\n"
        "基本体: box(长方体)、sphere(球体)、cylinder(圆柱)、cone(圆锥)、capsule(胶囊)\n"
        "有机形状:\n"
        "  tree — 程序化树木。参数: tree_config{...}。一棵树仅需 1 个 tree 零件即可生成完整繁茂的形态。\n"
        "  spline_tube — 样条管。参数: points[{x,y,z},...], radius。适合尾巴、触手、电缆、蛇、象鼻。\n"
        "  deformed — 噪声变形体。参数: displacement, spikes。适合岩石、山脉、陨石、有机肉块。\n"
        "  blob — 融合球（Metaballs）。参数: spheres[{x,y,z,radius},...]。多个球体融合成光滑整体，适合动物躯干、云朵、软体。\n"
        "\n═══ 建模策略案例（以汽车为例） ═══\n"
        "  - 车身主体：1个大 box (4.5x1.2x1.8)\n"
        "  - 车顶：1个稍微小一点的 box (3x0.6x1.6)\n"
        "  - 轮子：4个横放的 cylinder (直径0.6, 厚度0.3)\n"
        "  - 车灯：2个 emissive 的 sphere\n"
        "  - 车窗：4个扁平的黑色 box 或透明 box\n"
        "\n═══ 核心工作流 ═══\n"
        "输出 tool call 前，必须先用中文完成以下深度分析：\n"
        "【分析】视觉拆解目标：将目标拆解为哪些子模块？每个模块选用什么形状？预计使用多少个零件？如何确保它们互相接触不悬空？\n"
    )

async def generate_single_asset(actor_id: str, prompt: str, model: str = "astron-code-latest", progress_cb=None) -> str:
    """Generates a GLB for a single actor and returns the relative path."""
    def _cb(msg: str):
        if progress_cb:
            progress_cb(f"🧱 [{actor_id}] {msg}")

    _cb("AI 正在构思建模方案...")
    system = get_system_prompt()
    
    # Run LLM
    set_model(model)
    try:
        result = await asyncio.to_thread(llm_call, system, prompt, ai_model_tool)
    except Exception as e:
        print(f"[AssetGenerator] LLM failed for {actor_id}: {e}")
        return ""

    parts = result.get("parts", [])
    if not parts:
        _cb("⚠️ LLM 未返回零件数据")
        return ""

    _cb(f"组装 {len(parts)} 个零件 → GLB...")
    try:
        glb_bytes = await asyncio.to_thread(build_glb, parts)
    except Exception as e:
        print(f"[AssetGenerator] GLB build failed: {e}")
        return ""

    model_name = re.sub(r"[^\w\-]", "_", result.get("model_name", actor_id))
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    filename = f"{actor_id}_{model_name}.glb"
    dest = os.path.join(CUSTOM_DIR, filename)
    with open(dest, "wb") as f:
        f.write(glb_bytes)

    rel_path = os.path.relpath(dest, GODOT_DIR).replace("\\", "/")
    _cb(f"✅ 建模完成: {filename}")
    return rel_path
