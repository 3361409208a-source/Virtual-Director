from backend.services.llm import llm_call
from backend.tools.definitions import actor_tool


def run_actor_agent(prompt: str, director: dict, scene_ctx: dict) -> dict:
    """
    Worker B: Define actors and generate per-actor keyframe animation tracks.
    Must use the exact actor IDs provided by the director.
    Returns a dict containing 'actors' and 'actor_tracks'.
    """
    system = (
        "You are a world-class Animation Director. Respond in Chinese.\n\n"
        f"Task brief: {director['actors_brief']}\n"
        f"Actor IDs (use EXACTLY): {director['actor_ids']}\n"
        f"Duration: {director['meta']['total_duration']}s. Y=0 is ground.\n\n"
        "CRITICAL — make movement LARGE and DRAMATIC:\n"
        "- Actors must travel significant distances — a 5s video needs at LEAST 20-50m of Z displacement\n"
        "- Cars should go from z=0 to z=-80 or more; humans z=0 to z=-20; spacecraft z=0 to z=-200\n"
        "- Small movements (z only changes by 2-5m) look completely static on screen — AVOID\n\n"
        "Animation principles:\n"
        "- Ease-in/out: all moves must accelerate at start and decelerate at end, no constant speed\n"
        "- Anticipation: small counter-motion before the main action (crouch before jump, pullback before punch)\n"
        "- Follow-through: after launch/hit the body keeps rotating briefly; cars don't stop instantly after braking\n"
        "- Keyframe density: high-action moments need frames every 0.5s; calm transitions every 2s is enough\n\n"
        "Coordinate convention: main travel along Z axis (forward=negative). X=lateral, Y=altitude.\n\n"
        "Movement speed reference:\n"
        "- Human run: z ~-5 m/s; walk: z ~-1.5 m/s\n"
        "- Car: z -15 to -25 m/s during cruise\n"
        "- Aircraft takeoff: z:-100, y:0->80 over 8s, pitch rotation.x:-15\n"
        "- Orbital body: fix Y altitude, arc along Z or mix X+Z\n\n"
        "Attach system: use attach_to + local_offset for rider/passenger.\n"
        "Parent uses world coords; child after attach_to uses local offset coords only.\n\n"
        "Limb joints: use sub_tracks to rotate composite parts locally.\n"
        "Common angles: raise arm=rotation.x 90; turn head=rotation.y 30; bow=torso rotation.x 20"
    )
    return llm_call(system, prompt, actor_tool)


