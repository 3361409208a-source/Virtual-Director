import os
from backend.services.llm import llm_call
from backend.tools.definitions import asset_search_tool, asset_tool
from backend.config import GODOT_DIR

def run_asset_agent(prompt: str, director: dict, progress_cb=None, token_cb=None) -> dict:
    """
    Worker E: Two-phase asset pipeline.
    Phase 1 — LLM generates search queries per actor, then fetch GLB from open-source sites.
    Phase 2 — Composite fallback (box/sphere/cylinder) for actors that couldn't be fetched.
    """
    def _cb(msg: str):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    actors = director.get("actor_ids", [])
    brief  = director.get("asset_brief", "")
    manifest_dict: dict = {}

    # ── Phase 1: LLM decides search queries ───────────────────────────────────
    _cb("🔍 [资产AI] 分析演员特征，准备检索开源模型库...")
    search_system = (
        "You are a 3D asset search specialist. Respond in JSON only.\n"
        f"Scene brief: {brief}\n"
        f"Actor IDs: {actors}\n\n"

        "For EACH actor, provide the best English search query (1-3 words) to find a CC0 GLB model "
        "on Poly Pizza or Sketchfab, plus the target bounding-box size in meters.\n\n"

        "QUERY RULES:\n"
        "- Use the MOST COMMON noun only: 'car' not 'red sports car 2024 turbo'\n"
        "- Decode actor IDs: 'red_police_car' → query='police car'; 'fire_dragon' → query='dragon'\n"
        "- Use singular noun: 'tree' not 'trees'; 'rock' not 'rocks'\n"
        "- Avoid adjectives/colors/brands in the query — they reduce match rate\n"
        "- Best query examples: 'car' 'human' 'dragon' 'rocket' 'basketball' 'sword' 'tree' 'duck'\n"
        "- Anti-patterns (never use): 'red car' 'fast rocket ship 3D' 'low poly person walking'\n\n"

        "TARGET SIZE reference (meters, bounding box):\n"
        "human/humanoid : x=0.5  y=1.8  z=0.3\n"
        "car/truck/bus  : x=2.0  y=1.5  z=4.5\n"
        "motorcycle     : x=0.8  y=1.2  z=2.2\n"
        "airplane/jet   : x=30   y=5    z=25\n"
        "rocket         : x=3    y=12   z=3\n"
        "helicopter     : x=12   y=4    z=15\n"
        "dragon         : x=8    y=4    z=12\n"
        "horse          : x=1.5  y=1.8  z=2.5\n"
        "dog/fox/cat    : x=0.5  y=0.5  z=0.8\n"
        "duck/bird      : x=0.3  y=0.3  z=0.4\n"
        "basketball     : x=0.24 y=0.24 z=0.24\n"
        "sword          : x=0.1  y=1.2  z=0.1\n"
        "tree           : x=3    y=8    z=3\n"
        "building/house : x=10   y=15   z=10\n"
        "rock/stone     : x=1    y=0.8  z=1\n"
        "default prop   : x=1    y=1    z=1"
    )
    try:
        search_plan = llm_call(search_system, prompt, asset_search_tool, token_cb=token_cb)
        searches = search_plan.get("searches", [])
    except Exception as e:
        print(f"[AssetAgent] search plan LLM failed: {e}")
        searches = [{"actor_id": a, "query": a.replace("_", " "), "target_size": {"x": 1, "y": 1, "z": 1}} for a in actors]

    # ── Phase 1b: Fetch from open-source sites ────────────────────────────────
    from backend.services.asset_fetcher import fetch_model

    fetched: set = set()
    for item in searches:
        actor_id = item.get("actor_id", "")
        query    = item.get("query", actor_id)
        size     = item.get("target_size", {"x": 1, "y": 1, "z": 1})
        if not actor_id:
            continue
        _cb(f"🌐 [资产AI] {actor_id} → 检索 \"{query}\"...")
        path = fetch_model(actor_id, query, on_progress=_cb)
        if path:
            rel = os.path.relpath(path, GODOT_DIR).replace("\\", "/")
            manifest_dict[actor_id] = {
                "actor_id":    actor_id,
                "type":        "downloaded",
                "path":        rel,
                "target_size": size,
            }
            fetched.add(actor_id)
            _cb(f"✅ [资产AI] {actor_id} 模型下载成功 → {os.path.basename(path)}")
        else:
            _cb(f"↪️ [资产AI] {actor_id} 下载失败，将用积木拼装")

    # ── Phase 2: Composite fallback for un-fetched actors ─────────────────────
    remaining = [a for a in actors if a not in fetched]
    if remaining:
        _cb(f"🧱 [资产AI] {remaining} 使用积木拼装...")
        system = (
            "You are a senior 3D Asset TD at a VFX studio. Respond in Chinese.\n\n"
            f"Asset brief: {brief}\n"
            f"Actor IDs to design (composite only): {remaining}\n\n"
            "Build every actor from: box (cuboid), sphere (ball), cylinder (tube/wheel).\n"
            "Shape rules: sphere for heads/balls/planets; cylinder for wheels/barrels; box for body/chassis.\n"
            "Name every part, use parent_name for joint hierarchy.\n"
            "Proportion: human torso {x:0.5,y:0.9,z:0.3} | car chassis {x:1.8,y:0.5,z:4.2}.\n"
            "Match real-world colors: skin r=0.9g=0.75b=0.6, metal r=0.7g=0.72b=0.75.\n"
            "Coordinate: Y=up, Z=forward, X=right."
        )
        try:
            result = llm_call(system, prompt, asset_tool)
            for item in result.get("asset_manifest", []):
                aid = item.get("actor_id")
                if aid and aid not in manifest_dict:
                    manifest_dict[aid] = item
        except Exception as e:
            print(f"[AssetAgent] composite fallback failed: {e}")

    # Fill any still-missing actors
    for a in actors:
        if a not in manifest_dict:
            manifest_dict[a] = None

    print(f"[AssetAgent] 完成: {len(fetched)} 下载 + {len(remaining)} 积木")
    return {"asset_manifest": manifest_dict}
