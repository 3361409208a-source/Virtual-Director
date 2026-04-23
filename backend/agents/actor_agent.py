from backend.services.llm import llm_call
from backend.tools.definitions import actor_tool


def run_actor_agent(prompt: str, director: dict, scene_ctx: dict) -> dict:
    """
    Worker B: Define actors and generate per-actor keyframe animation tracks.
    Must use the exact actor IDs provided by the director.
    Returns a dict containing 'actors' and 'actor_tracks'.
    """
    system = (
        f"你是专业动作导演。任务简报: {director['actors_brief']}\n"
        f"演员ID列表（必须严格使用）: {director['actor_ids']}\n"
        f"视频时长: {director['meta']['total_duration']}秒。Y=0 为地面。\n"
        "【重要坐标约定】：除非简报另有说明，飞行、冲刺等主要运动轨迹应沿 Z 轴（如 z:0 -> z:-100）。\n"
        "碰撞/撞飞效果用关键帧模拟：被撞瞬间 position + rotation 剧变，飞出抛物线。"
    )
    return llm_call(system, prompt, actor_tool)
