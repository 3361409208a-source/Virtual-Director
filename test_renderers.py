"""
渲染器快速测试脚本
用法:
    python test_renderers.py godot       # 只测 Godot
    python test_renderers.py blender     # 只测 Blender
    python test_renderers.py             # 两个都测
"""

import sys
import os
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

OUTPUT_DIR = os.path.join(ROOT, "frontend", "public")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 最小测试 sequence ──────────────────────────────────────────────────────────
SEQUENCE = {
    "meta": {
        "total_duration": 3.0,
        "fps": 12
    },
    "scene_setup": {
        "sky": {
            "top_color":     {"r": 0.1, "g": 0.3, "b": 0.7},
            "horizon_color": {"r": 0.5, "g": 0.7, "b": 0.9}
        },
        "fog": {"enabled": False, "density": 0.0, "color": {"r": 1, "g": 1, "b": 1}},
        "ground": {"size": 40, "color": {"r": 0.2, "g": 0.5, "b": 0.2}},
        "lights": [
            {"type": "sun", "energy": 2.0, "direction": {"x": -0.5, "y": -1.0, "z": -1.0}}
        ],
        "props": []
    },
    "actors": [
        {
            "id": "test_box",
            "type": "vehicle",
            "initial_position": {"x": 0, "y": 0, "z": 0},
            "initial_rotation": {"x": 0, "y": 0, "z": 0}
        }
    ],
    "actor_tracks": {
        "test_box": [
            {"time": 0.0, "position": {"x": 0,   "y": 0, "z": 0},   "rotation": {"x": 0, "y": 0, "z": 0}},
            {"time": 1.5, "position": {"x": 0,   "y": 0, "z": 50},  "rotation": {"x": 0, "y": 0, "z": 0}},
            {"time": 3.0, "position": {"x": 0,   "y": 0, "z": 100}, "rotation": {"x": 0, "y": 0, "z": 0}},
        ]
    },
    "camera_track": [
        {"time": 0.0, "mode": "static_look", "position": {"x": 30, "y": 10, "z": 30}, "look_at": {"x": 0, "y": 0, "z": 50}},
        {"time": 3.0, "mode": "static_look", "position": {"x": 30, "y": 10, "z": 80}, "look_at": {"x": 0, "y": 0, "z": 100}},
    ],
    "physics_objects": [],
    "asset_manifest": {}
}


def _ok(name, t):
    print(f"\n  ✅  [{name}] 渲染成功  ({t:.1f}s)\n")


def _fail(name, e):
    print(f"\n  ❌  [{name}] 渲染失败:\n")
    traceback.print_exc()
    print()


# ── Godot 测试 ─────────────────────────────────────────────────────────────────
def test_godot():
    print("=" * 55)
    print("  测试 Godot 渲染器")
    print("=" * 55)
    try:
        from backend.services.renderer import do_godot, do_ffmpeg
        from backend.config import SEQUENCE_PATH
        import json
        avi_path = os.path.join(OUTPUT_DIR, "test_godot.avi")
        mp4_path = os.path.join(OUTPUT_DIR, "test_godot.mp4")
        with open(SEQUENCE_PATH, "w", encoding="utf-8") as f:
            json.dump(SEQUENCE, f, ensure_ascii=False, indent=2)
        t0 = time.time()
        do_godot(avi_path)
        do_ffmpeg(avi_path, mp4_path)
        _ok("Godot", time.time() - t0)
        print(f"  输出文件: {mp4_path}")
        return True
    except Exception as e:
        _fail("Godot", e)
        return False


# ── Blender 测试 ───────────────────────────────────────────────────────────────
def test_blender():
    print("=" * 55)
    print("  测试 Blender 渲染器")
    print("=" * 55)
    try:
        from backend.services.renderer_blender import do_blender
        mp4_path = os.path.join(OUTPUT_DIR, "test_blender.mp4")
        t0 = time.time()
        do_blender(SEQUENCE, mp4_path)
        _ok("Blender", time.time() - t0)
        print(f"  输出文件: {mp4_path}")
        return True
    except Exception as e:
        _fail("Blender", e)
        return False


# ── 入口 ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    results = {}
    if arg in ("godot", "all"):
        results["Godot"]   = test_godot()
    if arg in ("blender", "all"):
        results["Blender"] = test_blender()

    print("=" * 55)
    print("  测试汇总")
    print("=" * 55)
    for name, ok in results.items():
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"  {status}  {name}")
    print()
    sys.exit(0 if all(results.values()) else 1)
