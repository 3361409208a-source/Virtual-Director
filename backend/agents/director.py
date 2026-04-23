import json
from backend.services.llm import llm_call
from backend.tools.definitions import director_tool


def run_director(prompt: str, scene_ctx: dict) -> dict:
    """
    Phase 1: Analyze the user's prompt and decompose it into briefs for three
    worker agents (scene, actor, camera).  Also decides total duration and actor IDs.
    """
    system = (
        "你是制片总监。分析用户意图，拆解为布景/动作/镜头三个任务简报，"
        "确定视频时长和所有演员ID列表。\n"
        "【极其重要规则】：为确保动作AI与布景AI的一致性，请在拆解任务时，明确规定坐标系约定！"
        "例如：所有跑道、主干道、飞行轨迹必须严格沿 Z 轴（如从 z:0 到 z:-100），"
        "不允许沿 X 轴飞行/行驶。左右间隔使用 X 轴，高度使用 Y 轴。\n"
        f"场景能力说明: {json.dumps(scene_ctx, ensure_ascii=False)}"
    )
    return llm_call(system, prompt, director_tool)
