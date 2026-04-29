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
        "  tree — 程序化树木，自动生成树干+分支+树叶。参数: tree_config{trunk_height, trunk_radius, branch_levels, branch_count, branch_spread, leaf_type, leaf_size, trunk_color, leaf_color, seed}\n"
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
        "\n═══ 拼装规范 ═══\n"
        "- 原点(0,0,0)=模型底部中心，Y朝上\n"
        "- 人形：身高1.8m，躯干capsule{x:0.45,y:0.6,z:0.25}@y=0.6 | 头sphere{x:0.25}@y=1.4\n"
        "- 车辆：车身box{x:1.8,y:0.5,z:4.0} | 4轮cylinder@四角\n"
        "- 树木：1个tree零件，size指定整体包围盒，tree_config指定参数\n"
        "- 动物：blob做身体 + sphere做头 + spline_tube做尾巴 + capsule做四肢\n"
        "\n═══ 有机形状示例 ═══\n"
        "橡树: shape=tree, size{x:3,y:5,z:3}, tree_config{trunk_height:3, trunk_radius:0.2, branch_levels:3, leaf_type:sphere, leaf_size:0.8, trunk_color{r:0.4,g:0.25,b:0.1}, leaf_color{r:0.15,g:0.55,b:0.1}}\n"
        "岩石: shape=deformed, size{x:1.5,y:1,z:1.2}, displacement:0.25, seed:42, color{r:0.5,g:0.5,b:0.48}\n"
        "猫身体: shape=blob, size{x:0.6,y:0.4,z:1.2}, blob_config{spheres:[{x:0,y:0.2,z:0.3,radius:0.25},{x:0,y:0.2,z:-0.2,radius:0.2}]}\n"
        "尾巴: shape=spline_tube, size{x:0.1,y:0.6,z:0.5}, points:[{x:0,y:0.3,z:-0.4},{x:0.1,y:0.5,z:-0.7},{x:0,y:0.6,z:-0.9}], radius:0.03\n"
        "\n═══ 颜色精准匹配 ═══\n"
        "- 红(0.9,0.1,0.1) | 金属(0.6,0.62,0.65) | 皮肤(0.9,0.75,0.6) | 金(0.85,0.7,0.2)\n"
        "- 树干棕(0.4,0.25,0.1) | 树叶绿(0.15,0.55,0.1) | 岩石灰(0.5,0.5,0.48) | 草地(0.3,0.6,0.15)\n"
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
