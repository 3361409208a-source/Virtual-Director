from backend.services.llm import llm_call
from backend.tools.definitions import actor_tool


def run_actor_agent(prompt: str, director: dict, scene_ctx: dict, token_cb=None) -> dict:
    """
    Worker B: Define actors and generate per-actor keyframe animation tracks.
    Must use the exact actor IDs provided by the director.
    Returns a dict containing 'actors' and 'actor_tracks'.
    """
    system = (
        "你是好莱坞级别的动画总监（Animation Director）。\n\n"

        f"【任务简报】：{director['actors_brief']}\n"
        f"【演员ID（必须原样使用）】：{director['actor_ids']}\n"
        f"【片长】：{director['meta']['total_duration']}s。Y=0 为地面基准。\n\n"

        "【演员 type 选择指南】：\n"
        "humanoid → 所有人形角色（人、士兵、运动员、机器人）\n"
        "car       → 所有地面载具（轿车、卡车、坦克、摩托）\n"
        "plane     → 所有飞行体（飞机、火箭、飞船、无人机）\n"
        "box       → 通用物体/道具（箱子、岩石、球、爆炸碎片）\n\n"

        "【位移幅度强制要求】：\n"
        "步行：Z 位移 ≥ 20m；跑步：Z 位移 ≥ 35m；\n"
        "汽车/跑道：Z 位移 ≥ 80m；高速行驶 ≥ 120m；\n"
        "飞行/太空：Z 位移 ≥ 200m，Y 高度须同步爬升。\n"
        "位移过小（<5m）会导致画面完全静止——这是最严重的质量缺陷。\n\n"

        "【关键帧动画原则】：\n"
        "缓入缓出：所有运动开头加速、结尾减速，避免匀速；\n"
        "预期动作：跳跃前下蹲(y:-0.3)，出拳前肘部回拉，起飞前速度骤增；\n"
        "跟随动作：刹车后车身继续前倾(rotation.x:+8)再回正；飞船点火后尾焰角度微抖；\n"
        "关键帧密度：高动作段每 0.3-0.5s 一帧；平稳段每 1.5-2s 一帧。\n\n"

        "【移动速度参考（Z轴，负值=前进）】：\n"
        "人步行 ~-1.5 m/s；人跑步 ~-5 m/s；人冲刺 ~-9 m/s；\n"
        "自行车 ~-6 m/s；摩托 ~-20 m/s；汽车巡航 -18 to -25 m/s；赛车 -40 m/s；\n"
        "螺旋桨飞机 -50 m/s；喷气机 -120 m/s；火箭发射 0→-200 m/s（加速段）；\n"
        "太空轨道体：保持 Y 高度，Z 以 -30 to -80 m/s 匀速。\n\n"

        "【载具姿态（rotation）规范】：\n"
        "汽车入弯：rotation.y 顺弯方向 ±15-25°，同时车身侧倾 rotation.z ±5-8°；\n"
        "飞机爬升：rotation.x -10 to -20°（机头上仰）；俯冲：rotation.x +15 to +30°；\n"
        "飞机转弯：rotation.z ±20-45°（坡度滚转）+ rotation.y 转向；\n"
        "火箭垂直起飞：初始 rotation.x=0，逐步倾斜至 rotation.x=-15°（重力转弯）。\n\n"

        "【Y 轴高度档位（飞行场景）】：\n"
        "起飞滑跑：y=0；离地：y=3-5；低空飞行：y=20-50；高空巡航：y=80-200；太空：y=500+。\n"
        "飞行物 t=0 时的 initial_position.y 须与简报中的起飞/高度描述一致。\n\n"

        "【多演员交互规则】：\n"
        "追逐：领先者先出发(t=0)，追者延迟 0.5-1s 启动，两者 Z 坐标差保持 5-15m；\n"
        "超车：追者在 Z 差缩至 2m 时从 x 轴错位超过，再并回 x=0；\n"
        "碰撞：两者在相同 z 坐标 同一帧相遇，之后各自飞散（给 physics_agent 处理）；\n"
        "搭载（attach_to）：子演员坐标使用相对父演员的局部偏移；骑手 local_offset y=1.2。\n\n"

        "【复合模型肢体动画（sub_tracks）】：\n"
        "sub_tracks 键名为部件名称（与 asset manifest 的 parts.name 一致）；\n"
        "抬臂：sub_tracks.left_arm rotation.x=90°；转头：sub_tracks.head rotation.y=30°；\n"
        "车轮滚动：sub_tracks.wheel_fl rotation.x 随 Z 位移线性递增（每米转动 ~57°）；\n"
        "仅在有 composite 类型资产时使用 sub_tracks，下载模型无效果。"
    )
    return llm_call(system, prompt, actor_tool, token_cb=token_cb)


