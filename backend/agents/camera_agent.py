from backend.services.llm import llm_call
from backend.tools.definitions import camera_tool


def run_camera_agent(prompt: str, director: dict, token_cb=None) -> dict:
    """
    Worker C: Plan camera shots using runtime-tracking modes.
    The camera controller in Godot reads actor positions every frame,
    so 'follow'/'orbit'/'static_look' modes always stay on target.
    Returns a dict containing 'camera_track'.
    """
    actors = director["actor_ids"]
    duration = director["meta"]["total_duration"]
    first = actors[0] if actors else 'actor'
    system = (
        "你是好莱坞级别的摄影指导（Director of Photography）。\n\n"

        f"【镜头简报】：{director['camera_brief']}\n"
        f"【演员ID】：{actors}  |  【片长】：{duration}s\n\n"

        "【追踪模式说明（必须使用，禁止猜测演员绝对坐标）】：\n"
        f"follow      — 跟随目标演员，offset 控制相对角度。"
        f"示例：time=0, mode=follow, target_id='{first}', offset={{x:0,y:2,z:7}}, fov=65\n"
        f"orbit       — 环绕目标演员，适合高潮/冲击瞬间。"
        f"示例：mode=orbit, target_id='{first}', radius=6, height=3, orbit_speed=0.8, fov=55\n"
        "static_look  — 固定位置，镜头始终对准演员，最能展示运动穿越画面。"
        "示例：mode=static_look, position={x:8,y:1.5,z:0}, fov=60\n"
        "wide_look    — 俯瞰全体演员，定场/终场必用。"
        "示例：mode=wide_look, position={x:0,y:20,z:15}, fov=80\n\n"

        "【FOV 参考表】：\n"
        "史诗宽景：80-90；正常跟随：55-65；紧张/压迫：38-48；极端特写：25-35。\n"
        "FOV 变化规律：开场宽(80+) → 行动中等(60) → 高潮收紧(45-)。\n\n"

        "【offset 角度配方（follow 模式）】：\n"
        "标准后跟  {x:0,  y:2,  z:7}  — 人物/车辆正后方略高；\n"
        "低角仰拍  {x:0,  y:0.5,z:5}  — 英雄/起飞感；\n"
        "侧跟      {x:5,  y:1.5,z:4}  — 侧面展示角色；\n"
        "前方倒拍  {x:0,  y:1.5,z:-6} — 正面对冲/迎面；\n"
        "高空俯跟  {x:0,  y:12, z:3}  — 航拍风格。\n\n"

        "【多演员场景规则】：\n"
        "有 2+ 演员时，每段 static_look/follow 须明确 target_id 或 look_at_id；\n"
        "交互高潮（碰撞/相遇/超车）前 1-2s：切换到 static_look，让两者同时入镜；\n"
        "若需同时展示追逐双方，用 wide_look 或 static_look 侧面大 FOV；\n"
        "交互发生瞬间：用 transition=cut + orbit 环绕其中一个演员做特写反应镜头。\n\n"

        "【运动可见性原则（关键）】：\n"
        "static_look 是展示演员运动穿越的最佳模式——相机固定，演员在画面中划过；\n"
        "follow 把演员锁在中央，运动感只来自背景流动，用于追逐/跟拍；\n"
        "orbit 增加戏剧张力，用于高潮后的环绕特写；\n"
        "wide_look 定场/全景，不超过总时长的 20%。\n\n"

        "【电影构图规则】：\n"
        "180° 规则：整个片段保持相机在动作轴同侧；\n"
        "三分法：offset 偏移让主体处于画面三分线（y:1.5 而非 y:0）；\n"
        "cut 用于：冲击/爆炸/碰撞；smooth 用于：情绪积累/悬念推进。\n\n"

        "【四拍结构模板（≥ 4 关键帧，≥ 2 次模式切换）】：\n"
        f"t=0         wide_look  定场，高俯角建立环境 fov=82 smooth\n"
        f"t=时长×0.2  static_look 侧面固定，演员运动穿越画面 fov=62 cut\n"
        f"t=时长×0.5  follow      跟随主演员近距追拍 fov=58 smooth\n"
        f"t=时长×0.8  orbit       高潮时环绕特写 fov=48 cut\n"
        "以上为基础模板，可根据简报增加关键帧，但须遵守最少 4 帧 + 2 次模式切换。"
    )
    return llm_call(system, prompt, camera_tool, token_cb=token_cb)
