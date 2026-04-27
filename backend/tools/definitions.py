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
                        "fps":            {"type": "integer", "description": "帧率，推荐12（Blender CPU渲染，12fps已足够流畅）"},
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
                            "attach_to":  {
                                "type": "string",
                                "description": (
                                    "若该演员需要附着在另一个演员身上（如人骑在飞机/车上），"
                                    "填写被附着的演员ID。附着后，该演员的位置/旋转会完全跟随父演员，"
                                    "其 actor_tracks 应使用相对于父演员的局部坐标。"
                                    "不附着则省略此字段。"
                                ),
                            },
                            "local_offset": {
                                **VEC3,
                                "description": "attach_to 模式下，该演员相对于父演员中心的初始偏移量，如 {x:0,y:1,z:0} 表示在父演员上方1米处。",
                            },
                        },
                        "required": ["id", "type", "initial_position"],
                    },
                },
                "actor_tracks": {
                    "type": "object",
                    "description": "每个演员ID对应的关键帧列表。attach_to的演员的坐标为相对父演员的局部坐标（不附着的演员用世界坐标）。",
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

# ── Asset Search Tool ────────────────────────────────────────────────────────────
# Ask the LLM to decide which actors should be searched online and what queries to use.

asset_search_tool: dict = {
    "type": "function",
    "function": {
        "name": "plan_asset_searches",
        "description": (
            "为每个演员决定是否从开源3D模型库（Poly Pizza / Sketchfab）搜索现成的 GLB 模型。"
            "提供英文搜索关键词，尽量简洁（1-3个词），例如 'red car', 'basketball', 'dragon'。"
            "同时给出渲染时的目标缩放尺寸（米）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "searches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "actor_id":    {"type": "string",  "description": "演员ID"},
                            "query":       {"type": "string",  "description": "英文搜索关键词，如 'police car', 'basketball player'"},
                            "target_size": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"},
                                    "y": {"type": "number"},
                                    "z": {"type": "number"},
                                },
                                "description": "模型渲染目标尺寸（米），如人高1.8m → y=1.8",
                            },
                        },
                        "required": ["actor_id", "query", "target_size"],
                    },
                },
            },
            "required": ["searches"],
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
                            "type": {"type": "string", "enum": ["composite"], "description": "强制使用 composite 类型进行自定义模型拼装"},
                            "parts": {

                                "type": "array",
                                "description": "当 type 为 composite 时，给出用于拼装该物体的各个部件",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "部件名称，用于动画控制"},
                                        "parent_name": {"type": "string", "description": "父部件名称。如果设置了，该部件的位置将相对于父部件坐标系。用于构建关节点（如手臂挂在身体上）。"},
                                        "shape": {"type": "string", "enum": ["box", "sphere", "cylinder"]},
                                        "size": VEC3,
                                        "position": {**VEC3, "description": "相对局部坐标"},
                                        "rotation": {**VEC3, "description": "欧拉角旋转（度）"},
                                        "color": COLOR3
                                    },
                                    "required": ["name", "shape", "size", "position", "color"]
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

# ── AI Model Tool ─────────────────────────────────────────────────────────────
# Build a single standalone 3D model from natural language description.
# Returns a list of primitive parts that get assembled into a GLB file.

ai_model_tool: dict = {
    "type": "function",
    "function": {
        "name": "build_model",
        "description": (
            "根据自然语言描述，用 box/sphere/cylinder 基本体拼装一个 3D 模型。"
            "输出每个零件的形状、尺寸、位置、旋转和颜色。"
            "所有零件合并后就是这个模型的 GLB 文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": "模型名称（英文 snake_case，如 red_robot）"
                },
                "description": {
                    "type": "string",
                    "description": "对模型的简短中文描述，用于展示"
                },
                "parts": {
                    "type": "array",
                    "description": "构成该模型的所有零件",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":  {"type": "string",  "description": "零件名称，如 torso/head/wheel_fl"},
                            "shape": {"type": "string",  "enum": ["box", "sphere", "cylinder"],
                                      "description": "基本体形状"},
                            "size": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}
                                },
                                "description": "零件包围盒尺寸（米）"
                            },
                            "position": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}
                                },
                                "description": "零件中心在模型本地坐标系中的位置（米），Y=0 为模型底部"
                            },
                            "rotation": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}
                                },
                                "description": "零件旋转（欧拉角，度）"
                            },
                            "color": {
                                "type": "object",
                                "properties": {
                                    "r": {"type": "number"}, "g": {"type": "number"}, "b": {"type": "number"}
                                },
                                "description": "零件 RGB 颜色（0-1 浮点），如红色 r=1 g=0 b=0"
                            }
                        },
                        "required": ["name", "shape", "size", "position", "color"]
                    }
                }
            },
            "required": ["model_name", "description", "parts"]
        }
    }
}
