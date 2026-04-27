from backend.services.llm import llm_call
from backend.tools.definitions import camera_tool


def run_camera_agent(prompt: str, director: dict) -> dict:
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
        "You are a Hollywood-level Director of Photography (DP). Respond in Chinese.\n\n"
        f"Camera brief: {director['camera_brief']}\n"
        f"Actor IDs: {actors}  |  Duration: {duration}s\n\n"
        "ALWAYS use tracking modes — never guess absolute actor coordinates:\n"
        f"- follow: track target actor. offset controls angle. Example: time=0, mode=follow, "
        f"target_id='{first}', offset={{x:0,y:2,z:7}}, fov=65\n"
        "- orbit: revolve around target — best for climax/impact. "
        f"Example: mode=orbit, target_id='{first}', radius=6, height=3, orbit_speed=0.8, fov=55\n"
        "- static_look: locked position, lens always on actor — good for side/reaction shots. "
        "Example: mode=static_look, position={x:8,y:1.5,z:0}, fov=60\n"
        "- wide_look: high overview of all actors — best for establishing/finale. "
        "Example: mode=wide_look, position={x:0,y:15,z:12}, fov=75\n\n"
        "Cinematography rules:\n"
        "- Shot progression: open with wide_look (ELS/LS) to establish, then cut to follow (MS) "
        "for action, then orbit/static_look (CU/ECU) at the climax\n"
        "- 180 degree rule: keep camera on the same side of the action axis throughout a sequence\n"
        "- Rule of thirds: use offset to place subject off-center (e.g. y:1.5 instead of y:0)\n"
        "- FOV guidance: wide/epic=75-85, normal/follow=55-65, telephoto/tense=35-45\n"
        "- Transition: use 'smooth' for dramatic tension buildup; 'cut' for sudden impact/shock\n\n"
        "CRITICAL — making movement VISIBLE:\n"
        "- static_look is the BEST mode to show an actor moving: camera stays fixed while the actor\n"
        "  travels across the frame. Use it whenever an actor runs/drives/flies past.\n"
        "- follow mode keeps the actor centered — movement is implied NOT explicit. Only use follow\n"
        "  for chase scenes or when a slow reveal is intended.\n"
        "- orbit adds drama at the climax, after the action has already passed.\n\n"
        "Requirements:\n"
        "- Keyframe at t=0 is mandatory\n"
        "- MINIMUM 4 keyframes with at least 2 mode changes (no single mode the whole video)\n"
        "- Typical structure: t=0 wide_look (establish) → t=1s static_look (actor crosses) → "
        "t=mid follow (chase) → t=climax orbit (impact)\n"
        "- Impact moment: switch to orbit or static_look with transition=cut, fov tighten by 10-15"
    )
    return llm_call(system, prompt, camera_tool)
