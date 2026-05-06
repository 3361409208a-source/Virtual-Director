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
        base_ctx = f"\n参考底稿：{base_model}（以此为骨架，但必须进行大胆的超现实改造）\n"

    return (
        "你是享誉银河系的‘超现实数字生命架构师’。你的审美领先时代，拒绝平庸的堆砌。\n"
        "\n═══ [核心使命：注入奇异灵魂] ═══\n"
        "用户给出的描述只是基础。你的任务是在满足需求的基础上，**自动注入 1-2 种独一无二的奇异属性**：\n"
        "1. 【虚空悬浮】：设计一些不与主体物理连接的浮动组件（如悬浮的防御环、漂浮的能量晶体）。\n"
        "2. 【异质融合】：混合冲突的材质。例如在钢铁表面覆盖一层‘半透明的数字流体’或‘流动的岩浆脉络’。\n"
        "3. 【发光进化】：不仅仅是亮，而是设计‘发光骨架’或‘呼吸灯矩阵’。利用 emissive 强度创造视觉重心。\n"
        "4. 【非人造型】：如果建模生物，增加多余的关节、分叉的角或全息感官。如果建模机器，增加液压管线和裸露的核心。\n"
        "\n═══ [第一阶段：艺术总监构思日志] ═══\n"
        "在调用工具前，你必须输出一段中文【奇异设计日志】，向用户展示你的艺术决策：\n"
        "- 我为这个模型添加了什么样的【独特奇异属性】？\n"
        "- 它是如何利用【透明感】或【发光材质】来提升辨识度的？\n"
        "- 描述该物体的‘核心能量来源’是什么（全息？核能？魔法？）\n"
        "\n═══ [第二阶段：高精度参数输出] ═══\n"
        "- 【零件数量】：40-80 个，追求细节的极致复杂度。\n"
        "- 【材质极限】：尝试设置 roughness < 0.1 来模拟镜面/玻璃，或 metallic > 0.9 来模拟流态汞。\n"
        "- 【光效控制】：必须使用 `emissive` 颜色为物体注入生命力。\n"
        f"{base_ctx}\n"
        "让每一个模型都像是一件价值连城的赛博艺术品。开始你的奇幻创作："
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
