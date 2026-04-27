import json
from backend.services.llm import llm_call
from backend.tools.definitions import scene_tool


def run_scene_agent(prompt: str, director: dict, scene_ctx: dict, token_cb=None) -> dict:
    """
    Worker A: Build the visual environment (sky, sun, fog, ground, props).
    Receives the director's scene_brief and the scene capability context.
    Returns a dict containing 'scene_setup'.
    """
    brief   = director['scene_brief']
    dur     = director['meta']['total_duration']
    system = (
        "你是好莱坞制作级别的美术指导（Production Designer）。"
        "你负责规划完整的视觉环境，包括天空、光照、大气、地面与道具。\n\n"
        f"【本场任务简报】：{brief}\n"
        f"【片长】：{dur} 秒\n\n"
        "【三点布光原则】（适配室外自然光版本）：\n"
        "- 主光（Key）：太阳/主光源，决定阴影方向，energy 建议 1.2-2.0\n"
        "- 辅光（Fill）：环境漫反射，ambient_energy 建议 0.3-0.6，避免过曝\n"
        "- 轮廓光（Rim/Back）：通过 sun euler 角度控制侧逆光以凸显轮廓\n\n"
        "【色温与天空预设参考】：\n"
        "- 晴天正午：sky top=(0.18,0.36,0.72) horizon=(0.62,0.74,0.90)，sun color=(1.0,0.97,0.85)\n"
        "- 黄昏/日落：sky top=(0.12,0.16,0.40) horizon=(0.95,0.45,0.15)，sun color=(1.0,0.55,0.2) energy=0.8\n"
        "- 阴天：sky top=(0.55,0.60,0.65) horizon=(0.70,0.72,0.74)，ambient_energy=0.7\n"
        "- 宇宙/太空：sky top=(0.01,0.01,0.02) horizon=(0.02,0.02,0.04)，ground=disabled，ambient_energy=0.4\n"
        "- 水下/夜间：fog enabled=true，density 0.03-0.08\n\n"
        "【地面与道具】：根据简报选择合适的地面颜色和纹理感（roughness），\n"
        "道具用 props 数组补充背景细节（建筑、树木、标志物），位置沿 Z 轴两侧分布。\n\n"
        "【坐标约定】：主干道/跑道沿 Z 轴延伸，X 轴为左右，Y=0 为地面。\n"
        f"场景系统参数表: {json.dumps(scene_ctx.get('scene_setup_capabilities', {}), ensure_ascii=False)}"
    )
    return llm_call(system, prompt, scene_tool, token_cb=token_cb)
