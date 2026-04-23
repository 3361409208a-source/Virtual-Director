import json
from backend.services.llm import llm_call
from backend.tools.definitions import scene_tool


def run_scene_agent(prompt: str, director: dict, scene_ctx: dict) -> dict:
    """
    Worker A: Build the visual environment (sky, sun, fog, ground, props).
    Receives the director's scene_brief and the scene capability context.
    Returns a dict containing 'scene_setup'.
    """
    system = (
        f"你是专业布景师。任务简报: {director['scene_brief']}\n"
        f"视频时长: {director['meta']['total_duration']}秒\n"
        "【重要坐标约定】：除非简报另有说明，跑道、主干道等应沿 Z 轴延伸。\n"
        f"场景能力: {json.dumps(scene_ctx.get('scene_setup_capabilities', {}), ensure_ascii=False)}"
    )
    return llm_call(system, prompt, scene_tool)
