import os
from backend.services.llm import llm_call
from backend.tools.definitions import asset_tool

def run_asset_agent(prompt: str, director: dict, progress_cb=None, token_cb=None) -> dict:
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

    system = (
        "You are a senior 3D Asset TD (Technical Director) at a VFX studio. Respond in Chinese.\n\n"
        f"Asset brief: {brief}\n"
        f"Actor IDs to design: {actors}\n\n"
        "MANDATORY: ALL actors use composite type only. No builtins.\n"
        "Build every actor from: box (cuboid), sphere (ball), cylinder (tube/wheel).\n\n"
        "Shape selection rules:\n"
        "- Spherical bodies (planet, ball, head, eye): MUST use sphere\n"
        "- Thin rods, antennas, wings, struts: flat box or thin cylinder\n"
        "- Fuselage, torso, chassis, hull: box\n"
        "- Wheels, rocket nozzles, tree trunks, barrel: cylinder\n\n"
        "Skeleton / joint hierarchy rules:\n"
        "- Name every part (e.g. 'torso', 'head', 'arm_L', 'wing_R')\n"
        "- Use parent_name to build joint hierarchy so the Animation Director can rotate sub-parts\n"
        "- Child position is relative offset from parent center; keep rotation pivot logical\n"
        "- Example human: torso(box) -> head(sphere,parent=torso) -> arm_L(cylinder,parent=torso)\n"
        "- Example car: chassis(box) -> wheel_FL(cylinder,parent=chassis,pos={x:-0.9,y:-0.4,z:0.7})\n\n"
        "Proportion reference:\n"
        "- Human: torso {x:0.5,y:0.9,z:0.3} | head radius 0.22 | arm cylinder r=0.08 h=0.65\n"
        "- Car: chassis {x:1.8,y:0.5,z:4.2} | wheel r=0.35 h=0.25\n"
        "- Satellite: main body {x:1,y:0.6,z:1.5} | solar panel {x:2,y:0.05,z:0.8}\n\n"
        "Color design: match real-world materials. Avoid flat grey. Examples:\n"
        "- Skin: r=0.9,g=0.75,b=0.60 | Metal: r=0.7,g=0.72,b=0.75 | Solar panel: r=0.1,g=0.15,b=0.5\n"
        "- Earth ocean: r=0.1,g=0.3,b=0.8 | Grass: r=0.2,g=0.55,b=0.15\n\n"
        "Coordinate system: center=(0,0,0), Y=up, Z=forward/back, X=left/right."
    )


    _cb("⚡ 资产AI 正在分析并设计模型拼装图纸...")
    
    try:
        result = llm_call(system, prompt, asset_tool, token_cb=token_cb)
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
