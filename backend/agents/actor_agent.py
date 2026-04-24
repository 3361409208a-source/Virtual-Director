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
        "碰撞/撞飞效果用关键帧模拟：被撞瞬间 position + rotation 剧变，飞出抛物线。\n"
        "【附着系统】：当剧情需要一个演员骑乘/站在另一个演员上时（如人在飞机上、人在车里），\n"
        "必须使用 attach_to 字段。例如：person_1 需要骑乘 plane_1，则：\n"
        "  - person_1.attach_to = 'plane_1'\n"
        "  - person_1.local_offset = 该人相对飞机中心的偏移量（如 {x:0,y:1.2,z:-0.5}，即驾驶舱位置）\n"
        "  - person_1 的 actor_tracks 坐标系为相对 plane_1 的局部坐标，若人不移动则所有关键帧 position 为 {x:0,y:0,z:0}\n"
        "  - plane_1 的 actor_tracks 正常使用世界坐标规划飞行轨迹\n"
        "附着的演员不需要重复规划与父演员相同的轨迹，只需规划自身在父演员上的相对动作（如挥手、坐下等）。\n"
        "【肢体/关节点动画】：对于复合模型(composite)，你可以通过 sub_tracks 字段控制其内部部件的旋转。\n"
        "  - 例如在 keyframe 中设置 sub_tracks: {'arm_R': {'rotation': {'x': 90, 'y': 0, 'z': 0}}} 来让右臂抬起。\n"
        "  - 结合 parent_name 层级，你可以实现走路、格斗、操纵杆等复杂动作。"
    )
    return llm_call(system, prompt, actor_tool)


