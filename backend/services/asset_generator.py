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
        "你是3D建模技术总监，擅长用基本体和有机形状生成器最大化还原复杂视觉形象。\n"
        "\n═══ 可用形状 ═══\n"
        "基本体: box(长方体)、sphere(球体)、cylinder(圆柱)、cone(圆锥)、capsule(胶囊=圆柱+半球端)\n"
        "有机形状:\n"
        "  tree — 程序化树木，自动生成树干+分支+树叶。参数: tree_config{trunk_height, trunk_radius, branch_levels, branch_count, branch_spread, leaf_type, leaf_size, trunk_color, leaf_color, fruit_count, fruit_color, seed}。注意：如果是果树，请直接设置 fruit_count，严禁手动在空中摆放水果以免悬空。\n"
        "  spline_tube — 样条管，沿3D曲线生成管状体。参数: points[{x,y,z},...], radius。适合: 尾巴/触手/藤蔓/蛇/象鼻\n"
        "  deformed — 噪声变形体，在球体基础上添加有机凹凸。参数: displacement(0.05-0.5), spikes(0-1), seed。适合: 岩石/山丘/陨石/仙人掌/有机团块\n"
        "  blob — 融合球，多个球体融合成光滑有机体。参数: blob_config{spheres[{x,y,z,radius},...], resolution}。适合: 动物身体/云朵/软体/泥巴\n"
        "\n可用材质：颜色(RGBA)、metallic(金属度0-1)、roughness(粗糙度0-1)、emissive(自发光)\n"
        + base_ctx +
        "\n═══ 核心工作流：先深度分析，再选择最佳形状 ═══\n"
        "输出tool call前，必须先用中文完成以下分析：\n"
        "\n【步骤1】视觉特征提取：列出描述中所有可识别的视觉特征，按重要性排序。\n"
        "\n【步骤2】形状选择策略：\n"
        "  - 树木/植物 → 优先用 tree 形状（1个零件即可生成完整树形）\n"
        "  - 动物身体 → 用 blob 做躯干 + spline_tube 做尾巴/四肢 + sphere 做头\n"
        "  - 岩石/山丘 → 用 deformed 形状\n"
        "  - 蛇/蠕虫/触手 → 用 spline_tube\n"
        "  - 人形/车辆/建筑 → 用基本体拼装\n"
        "  - 复杂有机体 → 混合使用有机形状+基本体\n"
        "\n【步骤3】零件预算：\n"
        "  - 使用有机形状时，零件数可大幅减少（一棵树=1个tree零件）\n"
        "  - 纯基本体拼装：18-35个零件\n"
        "  - 有机形状+基本体混合：8-20个零件即可达到很好效果\n"
        "\n═══ 拼装规范与禁忌 ═══\n"
        "- 【严禁悬空】所有零件必须互相接触或重叠！眼睛、鼻子、耳朵等装饰零件必须嵌入主体。如果头部半径为R，五官的偏移距离必须小于或接近R，严禁将五官放在离主体中心太远的地方。\n"
        "- 【坐标系】原点(0,0,0)=模型底部中心，Y轴朝上。X为左右，Z为前后。请确保模型正面朝向Z正方向。\n"
        "- 【人体标准】身高1.8m。躯干: capsule{x:0.45,y:0.6,z:0.25}@y=0.6 | 头: sphere{x:0.25,y:0.25,z:0.25}@y=1.4\n"
        "- 【五官比例】眼睛(sphere/box{0.05})应放在头部中心(y=1.4)的偏移位置，如 position{x:±0.1, y:1.45, z:0.2}。\n"
        "- 【有机形状】1个tree零件指定整体包围盒；blob适合平滑躯干；spline_tube适合长条物。\n"
        "\n═══ 颜色精准匹配 ═══\n"
        "- 红(0.9,0.1,0.1) | 金属(0.6,0.62,0.65) | 皮肤(0.9,0.75,0.6) | 金(0.85,0.7,0.2)\n"
        "- 树干(0.4,0.25,0.1) | 树叶(0.15,0.55,0.1) | 岩石(0.5,0.5,0.48) | 草地(0.3,0.6,0.15)\n"
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
