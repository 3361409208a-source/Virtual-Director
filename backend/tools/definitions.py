from backend.tools.schemas import VEC3, COLOR3, SCENE_SETUP_PROPS, ACTOR_KEYFRAME

# ── Director Tool ───────────────────────────────────────────────────────────────
# Decomposes the user's prompt into task briefs for the three worker agents.

director_tool: dict = {
    "type": "function",
    "function": {
        "name": "decompose_task",
        "description": "分析用户意图，拆解为布景/动作/镜头三个任务简报，确定时长和演员ID列表",
        "parameters": {
            "type": "object",
            "properties": {
                "meta": {
                    "type": "object",
                    "properties": {
                        "total_duration": {"type": "number", "description": "视频总时长（秒）"},
                        "fps":            {"type": "integer", "description": "帧率，推荐60"},
                    },
                    "required": ["total_duration", "fps"],
                },
                "actor_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "场景中所有演员ID，如 ['car_1','person_a','person_b']",
                },
                "scene_brief":   {"type": "string", "description": "给布景AI的简报"},
                "actors_brief":  {"type": "string", "description": "给动作AI的简报"},
                "camera_brief":  {"type": "string", "description": "给镜头AI的简报"},
                "physics_brief": {"type": "string", "description": "给物理AI的简报：哪些演员需要真实物理（抛物/碰撞/滚动），初速方向和力度大概是多少"},
                "asset_brief":   {"type": "string", "description": "给资产AI的简报：每个演员应该长什么样，用英文描述，如 'car_1: red police car, dragon_1: fire-breathing dragon'"},
            },
            "required": ["meta", "actor_ids", "scene_brief", "actors_brief", "camera_brief", "physics_brief", "asset_brief"],
        },
    },
}

# ── Scene Tool ──────────────────────────────────────────────────────────────────

scene_tool: dict = {
    "type": "function",
    "function": {
        "name": "build_scene",
        "description": "构建场景环境（天空/光照/雾/地面/道具）",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_setup": {
                    "type": "object",
                    "properties": SCENE_SETUP_PROPS,
                },
            },
            "required": ["scene_setup"],
        },
    },
}

# ── Actor Tool ──────────────────────────────────────────────────────────────────

actor_tool: dict = {
    "type": "function",
    "function": {
        "name": "build_actors",
        "description": "定义演员并生成每个演员的关键帧动画轨迹",
        "parameters": {
            "type": "object",
            "properties": {
                "actors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":               {"type": "string"},
                            "type":             {"type": "string", "enum": ["humanoid", "car", "box", "plane"]},
                            "initial_position": VEC3,
                            "initial_rotation": VEC3,
                        },
                        "required": ["id", "type", "initial_position"],
                    },
                },
                "actor_tracks": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": ACTOR_KEYFRAME,
                    },
                },
            },
            "required": ["actors", "actor_tracks"],
        },
    },
}

# ── Camera Tool ─────────────────────────────────────────────────────────────────
# Uses runtime-tracking modes so the camera always knows where actors actually are.
#
# Modes:
#   follow      – chase target_id with offset, look at look_at_id
#   orbit       – circle around target_id at radius/height, look at it continuously
#   static_look – fixed position, always look_at look_at_id (actor tracking)
#   wide_look   – fixed position, look at centroid of ALL actors
#   free        – classic absolute-position keyframe (fallback)

camera_tool: dict = {
    "type": "function",
    "function": {
        "name": "build_camera",
        "description": (
            "规划摄像机运镜，使用追踪模式让镜头始终精准跟踪演员，"
            "而不是猜测绝对坐标。第0秒必须有一个关键帧。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "camera_track": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "number", "description": "切换到此镜头的时间（秒）"},
                            "mode": {
                                "type": "string",
                                "enum": ["follow", "orbit", "static_look", "wide_look", "free"],
                                "description": (
                                    "follow=跟随追踪, orbit=环绕, "
                                    "static_look=固定位置但镜头追踪演员, "
                                    "wide_look=俯瞰全体, free=绝对坐标"
                                ),
                            },
                            "target_id": {"type": "string", "description": "追踪/环绕的演员ID（follow/orbit用）"},
                            "look_at_id": {"type": "string", "description": "镜头始终对准的演员ID"},
                            "offset": {**VEC3, "description": "follow模式下相对目标的偏移量，如 {x:0,y:2,z:6} 表示后上方"},
                            "position": {**VEC3, "description": "static_look/wide_look/free 的绝对位置"},
                            "radius":      {"type": "number", "description": "orbit 模式的环绕半径（米）"},
                            "height":      {"type": "number", "description": "orbit 模式的相机高度（米）"},
                            "orbit_speed": {"type": "number", "description": "orbit 模式的旋转速度（弧度/秒）"},
                            "fov":        {"type": "number", "description": "视角（度），正常55-75，特写35-50"},
                            "transition": {"type": "string", "enum": ["cut", "smooth"], "description": "cut=硬切, smooth=平滑过渡"},
                        },
                        "required": ["time", "mode", "fov"],
                    },
                },
            },
            "required": ["camera_track"],
        },
    },
}

# ── Physics Tool ─────────────────────────────────────────────────────────────────
# Determines which actors are driven by Godot's physics engine (RigidBody3D).
# body_type:
#   rigid  – full physics from t=0 (collisions, gravity, initial velocity)
#   static – immovable collider (walls, obstacles)
#   none   – no physics, driven by keyframe animation (default)

physics_tool: dict = {
    "type": "function",
    "function": {
        "name": "build_physics",
        "description": (
            "分析哪些演员需要真实物理模拟。"
            "rigid 体由 Godot 物理引擎驱动（碰撞/重力/弹跳），"
            "只需设置初始速度和物理属性，不需要关键帧。"
            "如果场景没有抛物/碰撞等物理需求，返回空列表即可。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "physics_objects": {
                    "type": "array",
                    "description": "需要物理模拟的演员列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "actor_id":   {"type": "string", "description": "演员ID，须与 actor_ids 中一致"},
                            "body_type":  {
                                "type": "string",
                                "enum": ["rigid", "static", "none"],
                                "description": "rigid=刚体, static=静态碰撞体, none=关键帧动画",
                            },
                            "mass":          {"type": "number", "description": "质量(kg)：人≈70, 车≈1200, 石头≈5"},
                            "friction":      {"type": "number", "description": "摩擦系数 0-1，冰≈0.05, 橡胶≈0.9"},
                            "bounce":        {"type": "number", "description": "弹性系数 0-1，皮球≈0.7, 石头≈0.1"},
                            "gravity_scale": {"type": "number", "description": "重力倍率，正常=1.0，失重=0"},
                            "initial_linear_velocity":  {**VEC3, "description": "初始线速度(m/s)，如{x:0,y:0,z:-10}=向前10m/s"},
                            "initial_angular_velocity": {**VEC3, "description": "初始角速度(rad/s)"},
                            "collision_shape": {
                                "type": "string",
                                "enum": ["box", "sphere", "capsule"],
                                "description": "碰撞形状：人=capsule, 车/箱=box, 球=sphere",
                            },
                        },
                        "required": ["actor_id", "body_type", "collision_shape"],
                    },
                },
            },
            "required": ["physics_objects"],
        },
    },
}

# ── Asset Tool ───────────────────────────────────────────────────────────────────
# AI decides search queries for each actor. The service then calls Poly Pizza API.
# use_builtin=true  → skip download, use procedural primitive model (instant)
# use_builtin=false → search Poly Pizza for a CC0 GLB model

asset_tool: dict = {
    "type": "function",
    "function": {
        "name": "plan_assets",
        "description": (
            "为每个演员规划3D模型。"
            "你可以使用引擎自带的 humanoid/car/box/plane，"
            "也可以使用基础形状(box/sphere/cylinder)自行拼装（如飞船、动物、复杂机器等）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asset_manifest": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "actor_id": {"type": "string", "description": "演员ID"},
                            "type": {"type": "string", "enum": ["builtin", "composite"], "description": "如果使用引擎原本的则选 builtin，如果是自行拼装的特殊物体则选 composite"},
                            "parts": {
                                "type": "array",
                                "description": "当 type 为 composite 时，给出用于拼装该物体的各个部件",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "部件名称"},
                                        "shape": {"type": "string", "enum": ["box", "sphere", "cylinder"]},
                                        "size": VEC3,
                                        "position": {**VEC3, "description": "部件相对于物体中心的局部坐标"},
                                        "rotation": {**VEC3, "description": "欧拉角旋转（度）"},
                                        "color": COLOR3
                                    },
                                    "required": ["shape", "size", "position", "color"]
                                }
                            }
                        },
                        "required": ["actor_id", "type"]
                    }
                }
            },
            "required": ["asset_manifest"]
        }
    }
}
