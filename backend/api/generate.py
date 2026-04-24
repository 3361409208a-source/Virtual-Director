import asyncio
import json
import os
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.config import SEQUENCE_PATH, FRONTEND_PUBLIC_DIR, RENDERER
from backend.models import PromptRequest
from backend.agents.director import run_director
from backend.agents.scene_agent import run_scene_agent
from backend.agents.actor_agent import run_actor_agent
from backend.agents.camera_agent import run_camera_agent
from backend.agents.physics_agent import run_physics_agent
from backend.agents.asset_agent import run_asset_agent
from backend.services.renderer import do_godot, do_ffmpeg
from backend.services.renderer_blender import do_blender
from backend.services.llm import set_model
from backend.services.project_store import (
    create_project, append_chat_entry, save_sequence, save_video, finalize_project
)

import json as _json

router = APIRouter()


def _emit(step: str, msg: str, **extra) -> str:
    payload = {"step": step, "msg": msg, **extra}
    return f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"


def _load_scene_context() -> dict:
    from backend.config import SCENE_CONTEXT_PATH
    try:
        with open(SCENE_CONTEXT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@router.post("/generate")
async def generate_video(req: PromptRequest):
    async def stream():
        avi_path = os.path.join(FRONTEND_PUBLIC_DIR, "output.avi")
        mp4_path = os.path.join(FRONTEND_PUBLIC_DIR, "output.mp4")
        pid = create_project(req.prompt, req.model)

        def _save(step: str, msg: str):
            append_chat_entry(pid, {"step": step, "msg": msg, "ts": int(time.time() * 1000)})

        try:
            set_model(req.model)
            ctx = _load_scene_context()

            # ── Phase 1: Director ─────────────────────────────────────────────
            m = f"🎯 [总导演] 审读剧本，拆解分镜... (模型: {req.model})"
            _save("director", m)
            yield _emit("director", m)
            director = await asyncio.to_thread(run_director, req.prompt, ctx)
            meta = director["meta"]
            m = f"✅ [总导演] 片长 {meta['total_duration']}s · 卡司 {director['actor_ids']} · 五组工作组待命"
            _save("director_done", m)
            yield _emit("director_done", m)

            # ── Phase 2: Workers (parallel) ───────────────────────────────────
            m = "⚡ [工作组] 场景美术 · 角色指导 · 摄影指导 · 物理特效 · 美术资产 — 五组同时开拍..."
            _save("workers", m)
            yield _emit("workers", m)

            # Shared event queue: ("result", name, data) | ("progress", step, msg)
            evt_q: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            async def _run(name: str, fn, *args):
                try:
                    result = await asyncio.to_thread(fn, *args)
                    await evt_q.put(("result", name, result))
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    await evt_q.put(("error", name, str(e)))


            def _asset_progress_cb(msg: str):
                asyncio.run_coroutine_threadsafe(
                    evt_q.put(("progress", "asset_progress", f"📦 [美术资产] {msg}")),
                    loop,
                )

            asyncio.create_task(_run("scene",   run_scene_agent,   req.prompt, director, ctx))
            asyncio.create_task(_run("actor",   run_actor_agent,   req.prompt, director, ctx))
            asyncio.create_task(_run("camera",  run_camera_agent,  req.prompt, director))
            asyncio.create_task(_run("physics", run_physics_agent, req.prompt, director))
            asyncio.create_task(_run("asset",   run_asset_agent,   req.prompt, director, _asset_progress_cb))

            labels = {
                "scene":   "🏗️ [场景美术]",
                "actor":   "🎭 [动画导演]",
                "camera":  "🎬 [摄影指导]",
                "physics": "⚡ [物理特效]",
                "asset":   "📦 [美术资产]",
            }
            worker_results: dict = {}
            while len(worker_results) < 5:
                event = await evt_q.get()
                etype = event[0]
                if etype == "result":
                    _, name, result = event
                    worker_results[name] = result
                    m = f"✅ {labels[name]} 完成"
                    _save(f"{name}_done", m)
                    yield _emit(f"{name}_done", m)
                elif etype == "error":
                    _, name, err_msg = event
                    raise RuntimeError(f"Worker {name} ({labels.get(name, name)}) failed: {err_msg}")
                else:
                    _, step, msg = event
                    _save(step, msg)
                    yield _emit(step, msg)


            # ── Phase 3: Merge ────────────────────────────────────────────────
            m = "🔗 [后期合成] 合并五轨数据..."
            _save("merge", m)
            yield _emit("merge", m)
            physics_objs   = worker_results["physics"].get("physics_objects", [])
            asset_manifest = worker_results["asset"].get("asset_manifest", {})
            sequence = {
                "meta":            meta,
                "scene_setup":     worker_results["scene"].get("scene_setup", {}),
                "actors":          worker_results["actor"].get("actors", []),
                "actor_tracks":    worker_results["actor"].get("actor_tracks", {}),
                "camera_track":    worker_results["camera"].get("camera_track", []),
                "physics_objects": physics_objs,
                "asset_manifest":  asset_manifest,
            }
            with open(SEQUENCE_PATH, "w", encoding="utf-8") as f:
                json.dump(sequence, f, ensure_ascii=False, indent=2)
            save_sequence(pid, sequence)
            rigid_count = sum(1 for p in physics_objs if p.get("body_type") == "rigid")
            m = f"✅ 整合完成 · {len(sequence['actors'])} 个演员 · {rigid_count} 个动力学体 · {len(sequence['camera_track'])} 个运镜节点"
            _save("merge_done", m)
            yield _emit("merge_done", m)

            # ── Phase 3.5: Send scene preview to frontend ─────────────────────
            m = "🗺️ 分镜预览已就绪"
            _save("scene_preview", m)
            yield _emit("scene_preview", m, sequence=sequence)

            # ── Phase 3.7: Generate Cover (SiliconFlow) ───────────────────────
            cover_path = os.path.join(FRONTEND_PUBLIC_DIR, "cover.jpg")
            # Wipe any stale cover from a previous run so we never reuse it silently.
            if os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                except OSError as e:
                    print(f"Failed to remove stale cover: {e}")
            m = "🎨 [视觉传达] 正在使用 Kolors 生成定制视频封面..."
            _save("cover", m)
            yield _emit("cover", m)
            try:
                from backend.services.image_gen import generate_cover_prompt, generate_cover_image
                # Safely extract brief, fallback to original prompt to ensure relevance
                scene_brief = director.get("scene_brief", meta.get("scene_brief", req.prompt))
                asset_brief = director.get("actors_brief", meta.get("actors_brief", ""))

                img_prompt = await asyncio.to_thread(
                    generate_cover_prompt, req.prompt, scene_brief, asset_brief
                )
                saved = await asyncio.to_thread(generate_cover_image, img_prompt, cover_path)
                if not saved or not os.path.exists(cover_path):
                    cover_path = None
            except Exception as e:
                print(f"Cover gen failed: {e}")
                cover_path = None

            # ── Phase 4 & 5: Render ───────────────────────────────────────────
            if RENDERER == "blender":
                m = "🎬 [渲染农场] Blender Cycles CPU 渲染中（每帧约 2s）..."
                _save("rendering", m)
                yield _emit("rendering", m)
                await asyncio.to_thread(do_blender, sequence, mp4_path)
                m = "✅ [渲染农场] Blender 渲染完成"
                _save("rendering_done", m)
                yield _emit("rendering_done", m)
            else:
                m = "🎬 [渲染农场] Godot 引擎输出中..."
                _save("rendering", m)
                yield _emit("rendering", m)
                await asyncio.to_thread(do_godot, avi_path)
                m = "✅ [渲染农场] 引擎输出完成"
                _save("rendering_done", m)
                yield _emit("rendering_done", m)

                # ── Phase 5: ffmpeg (Godot only) ──────────────────────────────
                m = "🔄 [输出压制] ffmpeg 封装母带 (包含定制封面)..."
                _save("converting", m)
                yield _emit("converting", m)
                await asyncio.to_thread(do_ffmpeg, avi_path, mp4_path, cover_path)


            m = "🎥 杀青！成片已送达右侧放映厅。"
            _save("done", m)
            vid = f"/output.mp4?t={int(time.time())}"
            save_video(pid, mp4_path)
            finalize_project(pid, video_copied=True)
            yield _emit("done", m, video_url=vid)

        except Exception as e:
            print(f"Error occurred: {repr(e)}")
            import traceback
            traceback.print_exc()
            m = f"❌ 出错了：{repr(e)}"
            _save("error", m)
            yield _emit("error", m)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
