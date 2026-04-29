from backend.services.llm import llm_call
from backend.tools.definitions import physics_tool


def run_physics_agent(prompt: str, director: dict, token_cb=None, model_override=None) -> dict:
    """
    Worker D: Decide which actors get Godot RigidBody3D physics.
    AI sets initial conditions only; Godot's physics engine handles trajectories.
    Returns a dict containing 'physics_objects' (may be empty list).
    """
    actors   = director["actor_ids"]
    duration = director["meta"]["total_duration"]
    brief    = director.get("physics_brief", "")

    system = (
        "你是好莱坞级别的 VFX 动力学技术总监（Dynamics TD）。\n\n"

        f"【物理简报】：{brief}\n"
        f"【演员ID】：{actors}  |  【片长】：{duration}s\n\n"

        "【决策矩阵——何时用真实物理 vs 关键帧】：\n"
        "✅ 用 rigid 物理：\n"
        "  - 自由落体（从高处掉落，不需要精确落点）\n"
        "  - 爆炸碎片（多个物体无规则散射）\n"
        "  - 滚动/弹跳（球类、桶、岩石在地面滚动）\n"
        "  - 碰撞后解体飞散（车祸碎片、击打飞出）\n"
        "  - 绳索/布料之外的刚体互碰\n"
        "❌ 用关键帧（禁止用 rigid）：\n"
        "  - 脚本化驾驶/行走（需要精确路径的运动）\n"
        "  - 轨道/太空飞行（无重力但有预定轨迹）\n"
        "  - 起飞/着陆（精确坐标控制）\n"
        "  - 任何演员需要精确到达某个坐标点的运动\n"
        "👉 原则：能用关键帧控制的就不用物理；物理只管『不确定性』场景。\n\n"

        "【物理参数参考表】：\n"
        "质量(kg)：人=70 | 车=1200 | 摩托=200 | 木箱=30 | 岩石=500 | 卫星=300 | 篮球=0.6\n"
        "gravity_scale：正常=1.0 | 月球=0.17 | 太空失重=0.0 | 水中=0.3 | 浮游=0.4\n"
        "bounce(弹性)：橡胶=0.85 | 皮球=0.75 | 木头=0.35 | 金属=0.25 | 混凝土=0.08\n"
        "friction(摩擦)：冰=0.05 | 草地=0.65 | 泥土=0.75 | 沥青=0.85 | 橡胶=0.92\n\n"

        "【初速度配方（initial_linear_velocity）】：\n"
        "向上抛出  ：{x:±2-5, y:+8-15, z:±2-5}\n"
        "爆炸碎片  ：各轴随机 ±10-30，距爆心越远越小\n"
        "车祸飞散  ：主轴 ±12-22，横轴 ±3-8，y: +3-8（腾空）\n"
        "落地滚动  ：{x:0, y:-2, z:-5}（斜角滚入）\n"
        "平抛掉落  ：{x:0, y:0, z:0}（纯自由落体，从高处初始化位置）\n\n"

        "【与 actor_tracks 的配合规则】：\n"
        "rigid 体的演员在 actor_tracks 中仍可有关键帧（在物理接管前驱动它）；\n"
        "例如：t=0 到 t=碰撞时刻 用关键帧控制移动，碰撞时刻 body_type 切为 rigid + 初速度；\n"
        "但一旦切为 rigid，就不再添加关键帧（物理引擎接管）。\n\n"

        "【常见错误警告】：\n"
        "⚠️ 不要对所有演员都加物理——绝大多数动画场景不需要任何 rigid 体；\n"
        "⚠️ 不要把汽车/人的行走运动设为 rigid，这会导致它们被重力直接压在地面无法移动；\n"
        "⚠️ gravity_scale=0 的物体不会掉落，适合太空，但不适合地面场景的抛物运动。\n\n"

        "若场景无物理需求，返回 physics_objects=[] 空列表即可，无需强行添加。\n"
        "Y=0 处有静态地面碰撞体（StaticBody3D），rigid 体不会穿地。"
    )

    return llm_call(system, prompt, physics_tool, token_cb=token_cb)
