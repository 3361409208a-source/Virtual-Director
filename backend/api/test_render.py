import asyncio
import json
import os
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal

router = APIRouter()

TEST_SEQUENCE = {
    "meta": {"total_duration": 3.0, "fps": 12},
    "scene_setup": {
        "sky": {
            "top_color":     {"r": 0.1, "g": 0.3, "b": 0.7},
            "horizon_color": {"r": 0.5, "g": 0.7, "b": 0.9}
        },
        "fog":    {"enabled": False, "density": 0.0, "color": {"r": 1, "g": 1, "b": 1}},
        "ground": {"size": 40, "color": {"r": 0.2, "g": 0.5, "b": 0.2}},
        "lights": [{"type": "sun", "energy": 2.0, "direction": {"x": -0.5, "y": -1.0, "z": -1.0}}],
        "props": []
    },
    "actors": [
        {"id": "test_box", "type": "vehicle",
         "initial_position": {"x": 0, "y": 0, "z": 0},
         "initial_rotation": {"x": 0, "y": 0, "z": 0}}
    ],
    "actor_tracks": {
        "test_box": [
            {"time": 0.0, "position": {"x": 0, "y": 0, "z": 0},   "rotation": {"x": 0, "y": 0, "z": 0}},
            {"time": 1.5, "position": {"x": 0, "y": 0, "z": 50},  "rotation": {"x": 0, "y": 0, "z": 0}},
            {"time": 3.0, "position": {"x": 0, "y": 0, "z": 100}, "rotation": {"x": 0, "y": 0, "z": 0}},
        ]
    },
    "camera_track": [
        {"time": 0.0, "mode": "static_look",
         "position": {"x": 30, "y": 10, "z": 30}, "look_at": {"x": 0, "y": 0, "z": 50}},
        {"time": 3.0, "mode": "static_look",
         "position": {"x": 30, "y": 10, "z": 80}, "look_at": {"x": 0, "y": 0, "z": 100}},
    ],
    "physics_objects": [],
    "asset_manifest": {}
}


class TestRenderRequest(BaseModel):
    renderer: Literal["godot", "blender"] = "godot"


def _emit(step: str, msg: str, **extra) -> str:
    payload = {"step": step, "msg": msg, **extra}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/test-render")
async def test_render(req: TestRenderRequest):
    async def stream():
        from backend.config import FRONTEND_PUBLIC_DIR
        mp4_path = os.path.join(FRONTEND_PUBLIC_DIR, f"test_{req.renderer}.mp4")

        yield _emit("testing", f"🧪 [测试] 使用 {req.renderer.upper()} 渲染器进行测试渲染（3秒·最小场景）...")

        try:
            if req.renderer == "blender":
                from backend.services.renderer_blender import do_blender

                _total_f = int(3.0 * 12)
                _frames_dir = mp4_path.replace(".mp4", "_frames")
                render_state: dict = {"done": False, "err": None}
                t0 = time.time()

                async def _run():
                    try:
                        await asyncio.to_thread(do_blender, TEST_SEQUENCE, mp4_path)
                    except Exception as exc:
                        render_state["err"] = exc
                    finally:
                        render_state["done"] = True

                asyncio.ensure_future(_run())
                while not render_state["done"]:
                    await asyncio.sleep(2.0)
                    elapsed = time.time() - t0
                    try:
                        fc = len([f for f in os.listdir(_frames_dir) if f.endswith(".png")]) if os.path.isdir(_frames_dir) else 0
                    except OSError:
                        fc = 0
                    if fc > 0:
                        pct = min(int(fc / _total_f * 100), 99)
                        yield _emit("testing", f"🎬 [Blender] 帧 {fc}/{_total_f} ({pct}%) · {elapsed:.0f}s")
                    else:
                        yield _emit("testing", f"🎬 [Blender] 初始化场景 · {elapsed:.0f}s")

                if render_state["err"]:
                    raise render_state["err"]

            else:
                from backend.services.renderer import do_godot, do_ffmpeg
                from backend.config import SEQUENCE_PATH, FRONTEND_PUBLIC_DIR
                avi_path = os.path.join(FRONTEND_PUBLIC_DIR, "test_godot.avi")
                import json as _j
                with open(SEQUENCE_PATH, "w", encoding="utf-8") as f:
                    _j.dump(TEST_SEQUENCE, f, ensure_ascii=False, indent=2)
                yield _emit("testing", "🎮 [Godot] 启动引擎...")
                await asyncio.to_thread(do_godot, avi_path)
                yield _emit("testing", "🎞️ [Godot] 合成 MP4...")
                await asyncio.to_thread(do_ffmpeg, avi_path, mp4_path)

            video_url = f"/api/test-video/{req.renderer}"
            yield _emit("test_done",
                        f"✅ [{req.renderer.upper()}] 测试渲染成功！",
                        video_url=video_url)

        except Exception as e:
            yield _emit("test_error", f"❌ [{req.renderer.upper()}] 测试失败: {e}")

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/test-video/{renderer}")
async def get_test_video(renderer: str):
    from fastapi.responses import FileResponse
    from backend.config import FRONTEND_PUBLIC_DIR
    path = os.path.join(FRONTEND_PUBLIC_DIR, f"test_{renderer}.mp4")
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(404, "测试视频不存在，请先运行测试")
    return FileResponse(path, media_type="video/mp4")
