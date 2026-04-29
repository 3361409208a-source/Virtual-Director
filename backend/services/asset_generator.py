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
        "你是3D建模技术总监，擅长用基本体最大化还原复杂视觉形象。\n"
        "可用形状：box(长方体)、sphere(球体)、cylinder(圆柱)、cone(圆锥)、capsule(胶囊=圆柱+半球端)\n"
        "可用材质：颜色(RGBA)、metallic(金属度0-1)、roughness(粗糙度0-1)、emissive(自发光)\n"
        + base_ctx +
        "\n═══ 核心工作流：先深度分析，再拼装 ═══\n"
        "输出tool call前，必须先用中文完成以下分析：\n"
        "\n【步骤1】视觉特征提取：列出描述中所有可识别的视觉特征，按重要性排序。\n"
        "\n【步骤2】近似策略：对每个特征，思考如何用基本体最佳近似。\n"
        "\n【步骤3】零件预算：由复杂度决定，建议使用 18-35 个零件，确保细节丰富且比例协调。\n"
        "\n═══ 拼装规范 ═══\n"
        "- 原点(0,0,0)=模型底部中心，Y朝上\n"
        "- 人形：身高1.8m，躯干capsule{x:0.45,y:0.6,z:0.25}@y=0.6 | 头sphere{x:0.25}@y=1.4\n"
        "- 车辆：车身box{x:1.8,y:0.5,z:4.0} | 4轮cylinder@四角\n"
        "\n═══ 颜色精准匹配 ═══\n"
        "- 红(0.9,0.1,0.1) | 金属(0.6,0.62,0.65) | 皮肤(0.9,0.75,0.6) | 金(0.85,0.7,0.2)\n"
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
