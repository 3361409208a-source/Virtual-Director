# ── Primitive JSON-Schema building blocks ──────────────────────────────────────

VEC3: dict = {
    "type": "object",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "z": {"type": "number"},
    },
    "required": ["x", "y", "z"],
}

COLOR3: dict = {
    "type": "object",
    "properties": {
        "r": {"type": "number"},
        "g": {"type": "number"},
        "b": {"type": "number"},
    },
    "required": ["r", "g", "b"],
}

# ── Composite schemas ───────────────────────────────────────────────────────────

SCENE_SETUP_PROPS: dict = {
    "sky": {
        "type": "object",
        "properties": {"top_color": COLOR3, "horizon_color": COLOR3},
    },
    "ambient_energy": {"type": "number", "description": "环境光强度 0.0~1.0"},
    "sun": {
        "type": "object",
        "properties": {
            "enabled":       {"type": "boolean"},
            "euler_degrees": VEC3,
            "color":         COLOR3,
            "energy":        {"type": "number"},
        },
    },
    "fog": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"},
            "color":   COLOR3,
            "density": {"type": "number"},
        },
    },
    "ground": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"},
            "color":   COLOR3,
            "size":    {"type": "number"},
        },
    },
    "props": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id":       {"type": "string"},
                "shape":    {"type": "string", "enum": ["box", "sphere", "cylinder"]},
                "position": VEC3,
                "size":     VEC3,
                "color":    COLOR3,
            },
            "required": ["id", "shape", "position", "size", "color"],
        },
    },
}

ACTOR_KEYFRAME: dict = {
    "type": "object",
    "properties": {
        "time":     {"type": "number"},
        "position": VEC3,
        "rotation": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
        },
        "sub_tracks": {
            "type": "object",
            "description": "针对复合模型(composite)中特定部件(parts)的动画。Key为部件name，Value为该部件在当前时刻的局部变换。",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "position": VEC3,
                    "rotation": VEC3,
                },
            },
        },
    },
    "required": ["time", "position"],
}

