from backend.services.llm import llm_call
from backend.tools.definitions import physics_tool


def run_physics_agent(prompt: str, director: dict, token_cb=None) -> dict:
    """
    Worker D: Decide which actors get Godot RigidBody3D physics.
    AI sets initial conditions only; Godot's physics engine handles trajectories.
    Returns a dict containing 'physics_objects' (may be empty list).
    """
    actors   = director["actor_ids"]
    duration = director["meta"]["total_duration"]
    brief    = director.get("physics_brief", "")

    system = (
        "You are a senior VFX Dynamics TD (Technical Director). Respond in Chinese.\n\n"
        f"Physics brief: {brief}\n"
        f"Actor IDs: {actors}  |  Duration: {duration}s\n\n"
        "Decision rule — use rigid body ONLY when Godot physics adds value over keyframes:\n"
        "  YES: free-fall, rolling, explosion debris, bouncing objects, ragdoll-style impact scatter\n"
        "  NO:  scripted walking, driving on a road, orbiting in space (use keyframes instead)\n\n"
        "Physics parameter reference:\n"
        "Mass table (kg):  human=70 | car=1200 | motorbike=200 | crate=30 | rock=500 | satellite=300\n"
        "gravity_scale:  normal=1.0 | low-gravity/moon=0.17 | zero-g/space=0.0 | floaty=0.4\n"
        "bounce (restitution): rubber=0.8 | wood=0.4 | metal=0.3 | concrete=0.1\n"
        "friction: ice=0.05 | dirt=0.7 | rubber-on-asphalt=0.9\n\n"
        "Initial velocity guidelines:\n"
        "- Throw/launch upward: y: +6 to +12 m/s + horizontal component\n"
        "- Explosion blast: all axes randomised +-8 to +-25 m/s depending on charge\n"
        "- Car crash debris: dominant axis +-10-20, cross-axis +-3-8\n"
        "- Gentle drop: y: -2 m/s (near-surface start)\n\n"
        "Ground (StaticBody3D) is always present at Y=0 — rigid bodies won't fall through.\n"
        "If no rigid physics is needed, return physics_objects as empty list."
    )

    return llm_call(system, prompt, physics_tool, token_cb=token_cb)
