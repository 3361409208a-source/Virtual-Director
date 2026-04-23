from backend.services.llm import llm_call
from backend.tools.definitions import camera_tool


def run_camera_agent(prompt: str, director: dict) -> dict:
    """
    Worker C: Plan camera shots using runtime-tracking modes.
    The camera controller in Godot reads actor positions every frame,
    so 'follow'/'orbit'/'static_look' modes always stay on target.
    Returns a dict containing 'camera_track'.
    """
    actors = director["actor_ids"]
    duration = director["meta"]["total_duration"]
    system = f"""你是专业摄影指导。任务简报: {director['camera_brief']}
演员ID列表: {actors}，视频时长: {duration}秒

【重要】请使用追踪模式，不要猜测演员的绝对坐标：
- follow      : 跟随目标演员，用 offset 控制角度（推荐主要模式）
  示例: time=0, mode=follow, target_id="{actors[0] if actors else 'actor'}", offset={{x:0,y:2,z:7}}, look_at_id="{actors[0] if actors else 'actor'}", fov=65
- orbit       : 环绕目标旋转，适合高潮/撞击时刻
  示例: mode=orbit, target_id="...", radius=6, height=3, orbit_speed=0.8, fov=55
- static_look : 固定机位但镜头始终对准演员，适合侧面观察
  示例: mode=static_look, position={{x:8,y:1.5,z:0}}, look_at_id="...", fov=60
- wide_look   : 俯视全局，镜头对准所有演员重心，适合开场/结尾
  示例: mode=wide_look, position={{x:0,y:12,z:10}}, fov=75

第0秒必须有关键帧。
根据剧情节奏合理切换镜头（建议3-5个关键帧）。
撞击瞬间用 orbit 或 static_look 特写，transition 用 cut。"""
    return llm_call(system, prompt, camera_tool)
