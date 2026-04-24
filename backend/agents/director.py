import json
from backend.services.llm import llm_call
from backend.tools.definitions import director_tool


def run_director(prompt: str, scene_ctx: dict) -> dict:
    """
    Phase 1: Analyze the user's prompt and decompose it into briefs for three
    worker agents (scene, actor, camera).  Also decides total duration and actor IDs.
    """
    system = (
        "你是好莱坞级别的制片总监（Executive Producer + Director）。"
        "你的职责是将用户的创意意图转化为可执行的分镜指令包，分发给下游五个专项AI组。\n\n"
        "【叙事结构】：按三幕式拆解："
        "第一幕建立（开场建立环境与角色）、第二幕发展（核心动作/冲突/运动）、第三幕收尾（高潮或静止落幅）。"
        "scene_brief/actors_brief/camera_brief 均需体现三幕节奏，不得只描述高潮片段。\n\n"
        "【场景规模校准】："
        "室内/近景场景主轴 Z 跨度 10-30m；街道/跑道 30-100m；空中/宇宙 100-500m。"
        "脱离地面的场景（宇宙、飞行）需在 scene_brief 中明确注明 ground=disabled。\n\n"
        "【坐标约定（必须在三份 brief 中重申）】："
        "Z 轴为主运动方向（前进为负值）；X 轴为左右；Y 轴为高度，Y=0 为地面基准。"
        "所有主要位移轨迹沿 Z 轴，严禁沿 X 轴飞行或行驶。\n\n"
        "【brief 质量标准】：每份 brief 不少于 2 句，需包含："
        "①核心视觉目标 ②关键时间节点（如 t=0s/t=3s/t=8s 发生什么）③数量级参考（如高度约 200m、速度约 30m/s）。\n\n"
        f"场景系统能力说明: {json.dumps(scene_ctx, ensure_ascii=False)}"
    )
    return llm_call(system, prompt, director_tool)
