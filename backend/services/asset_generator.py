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
        "\n═══ [第三阶段：骨骼化规范 (重要)] ═══\n"
        "为了让模型能够被后端算法正确识别并添加动作，你必须：\n"
        "1. 【标准姿态】：如果是人型或生物，必须采用标准的 T-Pose（双臂平举）。确保模型垂直站立，正向朝向 Z 轴。\n"
        "2. 【语义化命名】：零件的 `name` 字段必须包含识别关键词。例如：\n"
        "   - 头部：head, neck, helmet\n"
        "   - 躯干：torso, spine, chest, hips\n"
        "   - 手臂：left_arm, right_arm, hand, shoulder\n"
        "   - 腿部：left_leg, right_leg, foot, knee\n"
        "3. 【物理结构】：尽量避免零件之间产生深度穿插。如果是关节部位（如肘部、膝部），在连接处稍微留出空隙或使用明显的转折件。\n"
        "\n═══ [第四阶段：关节坐标对齐规范（人形必须严格遵守）] ═══\n"
        "后端骨骼算法使用模型包围盒自动定位骨骼。为使骨骼与关节完全对齐，\n"
        "人形模型必须使用以下标准尺寸，且各身体部位中心必须落在指定坐标范围内：\n"
        "【标准尺寸】总高度 1.8m（y: 0→1.8），T-Pose 总臂展 1.44m（x: -0.72→+0.72），坐标原点在脚底中心。\n"
        "【各部位零件 position 中心坐标参考】\n"
        "  头部零件      : x ∈ [-0.14, 0.14],  y ∈ [1.48, 1.80]\n"
        "  颈部零件      : x ∈ [-0.09, 0.09],  y ∈ [1.30, 1.48]\n"
        "  胸腔/上躯干   : x ∈ [-0.20, 0.20],  y ∈ [1.05, 1.30]\n"
        "  腰腹/下躯干   : x ∈ [-0.18, 0.18],  y ∈ [0.82, 1.05]\n"
        "  骨盆/臀部     : x ∈ [-0.16, 0.16],  y ∈ [0.72, 0.88]\n"
        "  左上臂        : x ∈ [-0.38, -0.12], y ∈ [1.10, 1.24]  ← 中心应约 (-0.25, 1.17)\n"
        "  左下臂        : x ∈ [-0.58, -0.28], y ∈ [1.10, 1.24]  ← 中心应约 (-0.43, 1.17)\n"
        "  左手          : x ∈ [-0.76, -0.48], y ∈ [1.08, 1.22]  ← 中心应约 (-0.62, 1.17)\n"
        "  右上臂        : x ∈ [0.12, 0.38],   y ∈ [1.10, 1.24]  ← 中心应约 (+0.25, 1.17)\n"
        "  右下臂        : x ∈ [0.28, 0.58],   y ∈ [1.10, 1.24]  ← 中心应约 (+0.43, 1.17)\n"
        "  右手          : x ∈ [0.48, 0.76],   y ∈ [1.08, 1.22]  ← 中心应约 (+0.62, 1.17)\n"
        "  左大腿        : x ∈ [-0.22, -0.08], y ∈ [0.52, 0.76]  ← 中心应约 (-0.16, 0.67)\n"
        "  左小腿        : x ∈ [-0.22, -0.08], y ∈ [0.24, 0.52]  ← 中心应约 (-0.16, 0.38)\n"
        "  左脚          : x ∈ [-0.22, -0.05], y ∈ [0.00, 0.22]  ← 中心应约 (-0.16, 0.05)\n"
        "  右大腿        : x ∈ [0.08, 0.22],   y ∈ [0.52, 0.76]  ← 中心应约 (+0.16, 0.67)\n"
        "  右小腿        : x ∈ [0.08, 0.22],   y ∈ [0.24, 0.52]  ← 中心应约 (+0.16, 0.38)\n"
        "  右脚          : x ∈ [0.05, 0.22],   y ∈ [0.00, 0.22]  ← 中心应约 (+0.16, 0.05)\n"
        "【重要】违反坐标范围会导致骨骼动画错乱！装饰性悬浮零件不受限制。\n"
        "\n让每一个模型都像是一件价值连城的赛博艺术品。开始你的奇幻创作："
    )

async def generate_single_asset(actor_id: str, prompt: str, model: str = "astron-code-latest", progress_cb=None) -> dict:
    """Generates a GLB for a single actor.
    Returns {"path": rel_path, "abs_path": abs_path, "parts": [...]} or {} on failure.
    """
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
        return {}

    parts = result.get("parts", [])
    if not parts:
        _cb("⚠️ LLM 未返回零件数据")
        return {}

    _cb(f"组装 {len(parts)} 个零件 → GLB...")
    try:
        glb_bytes = await asyncio.to_thread(build_glb, parts)
    except Exception as e:
        print(f"[AssetGenerator] GLB build failed: {e}")
        return {}

    model_name = re.sub(r"[^\w\-]", "_", result.get("model_name", actor_id))
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    filename = f"{actor_id}_{model_name}.glb"
    dest = os.path.join(CUSTOM_DIR, filename)
    with open(dest, "wb") as f:
        f.write(glb_bytes)

    rel_path = os.path.relpath(dest, GODOT_DIR).replace("\\", "/")
    _cb(f"✅ 建模完成: {filename}")
    return {"path": rel_path, "abs_path": dest, "parts": parts}
