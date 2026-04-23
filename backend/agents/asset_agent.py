import os
from backend.services.llm import llm_call
from backend.tools.definitions import asset_tool

def run_asset_agent(prompt: str, director: dict, progress_cb=None) -> dict:
    """
    Worker E: Decide 3D model source for each actor.
    Generates composite shapes if needed.
    """
    def _cb(msg: str):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass
    
    actors = director.get("actor_ids", [])
    brief  = director.get("asset_brief", "")

    system = f"""你是3D资产策划师。任务简报: {brief}
演员列表: {actors}

【强制性规则】：
- 禁止使用 builtin 类型。即使是人(humanoid)、车(car)或飞机，也必须强制使用 composite 类型进行拼装。
- 你必须发挥空间想象力，使用 box（长方体）、sphere（球体）、cylinder（圆柱体）拼装出每一个演员的 3D 外形。
- 部件拼装示例：
  * 汽车：一个扁的长方体做底盘，一个短方块做车顶，四个圆柱体做轮子。
  * 小人：一个球体做头，一个垂直长方体做躯干，四个细长方块做手脚。
- 颜色选择：根据简报为每个部件设定生动的颜色。
- 坐标系：中心为 (0,0,0)，Y 为上，Z 为前后，X 为左右。"""


    _cb("⚡ 资产AI 正在分析并设计模型拼装图纸...")
    
    try:
        result = llm_call(system, prompt, asset_tool)
        manifest_array = result.get("asset_manifest", [])
        
        # Convert array to dict keyed by actor_id
        manifest_dict = {}
        for item in manifest_array:
            actor_id = item.get("actor_id")
            if actor_id:
                manifest_dict[actor_id] = item
                
        # Fill missing actors with None
        for actor_id in actors:
            if actor_id not in manifest_dict:
                manifest_dict[actor_id] = None
                
        print(f"[AssetAgent] 设计了 {len(manifest_dict)} 个演员的资产")
        return {"asset_manifest": manifest_dict}
    except Exception as e:
        print(f"[AssetAgent] 失败: {e}")
        manifest = {actor_id: None for actor_id in actors}
        return {"asset_manifest": manifest}
