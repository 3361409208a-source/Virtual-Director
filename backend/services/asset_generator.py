import os
import re
import json
import asyncio
from backend.services.llm import llm_call, set_model
from backend.tools.definitions import ai_model_tool
from backend.services.glb_builder import build_glb
from backend.config import GODOT_DIR
from backend.services.open3d_generator import Open3DGeneratorUnavailable, generate_open3d_asset

CUSTOM_DIR = os.path.join(GODOT_DIR, "assets", "custom")

def get_system_prompt(base_model: str = "") -> str:
    base_ctx = ""
    if base_model:
        base_ctx = f"\n参考模型名称：{base_model}（以此为灵感来源，但须按用户描述重新设计）\n"

    return (
        "你是世界顶尖的 3D 建模总监，曾在工业光魔或皮克斯负责数字资产架构。\n"
        "\n═══ [核心建模哲学：从构思到实体] ═══\n"
        "你认为‘积木式堆砌’是 3D 建模的耻辱。你追求的是通过‘程序化融合’与‘细节分层’创造真实感。\n"
        "\n═══ [第一阶段：深度建模构思（必须先执行）] ═══\n"
        "在调用建模工具前，你必须输出一段详细的中文【建模总监构思日志】，包含：\n"
        "1. 【视觉形态学拆解】：不仅是零件清单，而是分析主体的‘骨架流向’。例如角色应分为‘核心躯干、四肢肌群、关节连接器、外挂饰品’。\n"
        "2. 【高级技术应用】：明确说明哪些部位使用 `blob` 实现有机融合（如肌肉衔接），哪些使用 `spline_tube`（如血管、电缆），哪些使用 `deformed`（如岩石或伤痕）。\n"
        "3. 【PBR 材质逻辑】：定义整体的粗糙度与金属度分布，说明光线如何在该物体表面发生散射和反射。\n"
        "4. 【消除接缝策略】：解释你将如何安排零件重叠，以配合后端的‘体素融合引擎’生成完美皮肤。\n"
        "\n═══ [第二阶段：高精度参数输出] ═══\n"
        "1. 【零件数量】：强制 30-60 个零件，通过大量微小零件（如铆钉、缝隙、小支架）支撑真实感。\n"
        "2. 【材质参数】：必须为每个零件设置精细的 metallic 和 roughness（默认 0.5 太假，请按真实材质设定）。\n"
        "3. 【发光与自发光】：科幻或魔幻物体应合理利用 `emissive` 增加视觉重点。\n"
        "\n请记住：你的目标是让用户觉得这是一个‘被设计出来’的数字工艺品，而不是‘被凑出来’的方块。开始你的分析："
    )

async def generate_single_asset(actor_id: str, prompt: str, model: str = "astron-code-latest", progress_cb=None) -> str:
    """Generates a GLB for a single actor and returns the relative path."""
    def _cb(msg: str):
        if progress_cb:
            progress_cb(f"🧱 [{actor_id}] {msg}")

    _cb("尝试开源高精 3D 生成引擎...")
    try:
        open3d_result = await asyncio.to_thread(generate_open3d_asset, prompt, actor_id)
        rel_path = os.path.relpath(open3d_result["path"], GODOT_DIR).replace("\\", "/")
        _cb(f"✅ 开源高精建模完成: {open3d_result['filename']}")
        return rel_path
    except Open3DGeneratorUnavailable as e:
        _cb(f"开源高精引擎不可用，回退程序化建模: {e}")

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
