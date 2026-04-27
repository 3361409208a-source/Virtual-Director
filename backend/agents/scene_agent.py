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
        "你负责规划完整的视觉环境：天空、光照、大气、地面、雾与道具。\n\n"

        f"【本场任务简报】：{brief}\n"
        f"【片长】：{dur} 秒\n\n"

        "【三点布光原则（室外自然光版本）】：\n"
        "主光(Key)：太阳决定阴影方向，energy 1.2-2.0，energy<0.8 显得阴暗无力；\n"
        "辅光(Fill)：ambient_energy 0.3-0.6，过高(>0.8)导致无阴影全平光；\n"
        "轮廓光(Rim)：sun_rotation euler.y ±30-60° 实现侧逆光，凸显轮廓立体感。\n\n"

        "【天空与光照预设库（直接匹配使用）】：\n"
        "晴天正午  → sky_top(0.18,0.36,0.72) horizon(0.62,0.74,0.90) sun_color(1.0,0.97,0.85) energy=1.8 ambient=0.4\n"
        "黄昏日落  → sky_top(0.08,0.10,0.28) horizon(0.95,0.45,0.12) sun_color(1.0,0.52,0.18) energy=0.7 ambient=0.3\n"
        "清晨薄雾  → sky_top(0.55,0.68,0.88) horizon(0.90,0.88,0.80) sun_color(1.0,0.90,0.75) energy=0.9 fog_density=0.02\n"
        "阴天多云  → sky_top(0.52,0.56,0.62) horizon(0.68,0.70,0.72) ambient=0.72 energy=0.6\n"
        "夜晚月光  → sky_top(0.01,0.01,0.04) horizon(0.04,0.04,0.08) sun_color(0.7,0.8,1.0) energy=0.15 ambient=0.08\n"
        "宇宙太空  → sky_top(0.00,0.00,0.01) horizon(0.01,0.01,0.02) ambient=0.35 ground=disabled\n"
        "沙漠烈日  → sky_top(0.32,0.54,0.82) horizon(0.88,0.80,0.55) sun_color(1.0,0.98,0.80) energy=2.0\n"
        "暴风雨前  → sky_top(0.18,0.18,0.22) horizon(0.32,0.30,0.28) ambient=0.55 fog_density=0.025\n\n"

        "【雾/大气参数】：\n"
        "城市烟尘：fog enabled=true density=0.008-0.015；\n"
        "浓雾/神秘：density=0.03-0.06；\n"
        "太空/室外晴天：fog enabled=false。\n\n"

        "【地面材质参考】：\n"
        "柏油路：color(0.18,0.18,0.18) roughness=0.85；\n"
        "草地：color(0.22,0.45,0.15) roughness=0.90；\n"
        "沙漠/沙地：color(0.76,0.62,0.38) roughness=0.95；\n"
        "雪地：color(0.92,0.93,0.96) roughness=0.75；\n"
        "金属/跑道：color(0.40,0.40,0.42) roughness=0.55；\n"
        "水面：color(0.08,0.28,0.52) roughness=0.20。\n\n"

        "【道具布置策略】：\n"
        "道具应沿 Z 轴（演员运动方向）两侧对称或随机分布，产生纵深感；\n"
        "街道：每隔 15-25m 放路灯(x=±4)，每隔 30m 放建筑(x=±12)；\n"
        "跑道/公路：每隔 20m 放树木(x=±8)，远景可加山丘(x=±30,z=-100+)；\n"
        "太空：放置 3-5 个星球/陨石（大尺寸，距离 z=-200 至 z=-500）；\n"
        "道具 Y 坐标：地面物体 Y=0；悬挂/飘浮物体根据实际高度设定。\n\n"

        "【坐标约定】：主干道/跑道沿 Z 轴延伸，X 轴为左右，Y=0 为地面。\n\n"
        f"场景系统参数表: {json.dumps(scene_ctx.get('scene_setup_capabilities', {}), ensure_ascii=False)}"
    )
    return llm_call(system, prompt, scene_tool, token_cb=token_cb)
