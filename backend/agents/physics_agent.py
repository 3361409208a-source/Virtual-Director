from backend.services.llm import llm_call
from backend.tools.definitions import physics_tool


def run_physics_agent(prompt: str, director: dict) -> dict:
    """
    Worker D: Decide which actors get Godot RigidBody3D physics.
    AI sets initial conditions only; Godot's physics engine handles trajectories.
    Returns a dict containing 'physics_objects' (may be empty list).
    """
    actors   = director["actor_ids"]
    duration = director["meta"]["total_duration"]
    brief    = director.get("physics_brief", "")

    system = f"""你是专业的物理效果设计师。任务简报: {brief}
演员ID列表: {actors}，视频时长: {duration}秒

你的工作：决定哪些演员需要 Godot 刚体物理（碰撞/重力/弹跳），并设置初始条件。

【规则】
- Godot 物理引擎会自动计算轨迹，你只需提供初始速度和物理属性
- rigid 体不需要关键帧动画，引擎自动处理
- 如果演员只是走路/开车（已有关键帧），不需要 rigid，填 none 即可
- 适合 rigid 的场景：被抛出的物体、碰撞后飞散的碎片、自由落体、滚动的球
- 地面 Ground 已经是 StaticBody3D，rigid 体不会穿地

【速度参考】
- 步行: z方向 ±1.5 m/s
- 跑步: z方向 ±4 m/s  
- 汽车: z方向 ±10-20 m/s
- 抛出: y方向 +5-10 m/s (向上) + 水平分量
- 爆炸飞出: 各方向 ±5-20 m/s

如果场景没有需要物理的对象，返回 physics_objects 为空列表。"""

    return llm_call(system, prompt, physics_tool)
