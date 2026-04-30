import os
import re
import json
import shutil
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from backend.config import GODOT_DIR
from backend.services.llm import llm_call, set_model, get_token_usage
from backend.tools.definitions import ai_model_tool
from backend.services.glb_builder import build_glb
from backend.services.asset_generator import get_system_prompt
from backend.services.open3d_generator import Open3DGeneratorUnavailable, generate_open3d_asset

router = APIRouter()

_CATEGORIES = {
    "builtin":    os.path.join(GODOT_DIR, "assets", "builtin"),
    "downloaded": os.path.join(GODOT_DIR, "assets", "downloaded"),
    "custom":     os.path.join(GODOT_DIR, "assets", "custom"),
}

# ── List all models ──────────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    result = []
    for cat, dir_path in _CATEGORIES.items():
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.lower().endswith(".glb"):
                continue
            full = os.path.join(dir_path, fname)
            stat = os.stat(full)
            result.append({
                "id":       f"{cat}/{fname}",
                "category": cat,
                "filename": fname,
                "name":     os.path.splitext(fname)[0],
                "size_kb":  stat.st_size // 1024,
                "url":      f"/api/models/{cat}/{fname}",
                "mtime":    stat.st_mtime,
            })
    # Sort newest first
    result.sort(key=lambda m: m["mtime"], reverse=True)
    return {"models": result}


# ── Serve a model file ───────────────────────────────────────────────────────

@router.get("/models/{category}/{filename}")
def get_model_file(category: str, filename: str):
    if category not in _CATEGORIES:
        raise HTTPException(status_code=404, detail="Unknown category")
    if not filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only GLB files supported")
    path = os.path.join(_CATEGORIES[category], filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Model not found")
    return FileResponse(
        path,
        media_type="model/gltf-binary",
        filename=filename,
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ── Upload a custom model ────────────────────────────────────────────────────

@router.post("/models/upload")
async def upload_model(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only .glb files are accepted")
    custom_dir = _CATEGORIES["custom"]
    os.makedirs(custom_dir, exist_ok=True)
    dest = os.path.join(custom_dir, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size_kb = os.path.getsize(dest) // 1024
    return {
        "ok":       True,
        "filename": file.filename,
        "size_kb":  size_kb,
        "url":      f"/api/models/custom/{file.filename}",
    }


# ── AI Generate a model ──────────────────────────────────────────────────────

class AIGenerateRequest(BaseModel):
    prompt: str
    model: str = "astron-code-latest"
    base_model: str = ""   # optional reference model name
    engine: str = "procedural"  # procedural | open3d | auto

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

@router.post("/models/ai-generate")
async def ai_generate_model(req: AIGenerateRequest):
    """SSE streaming: streams LLM tokens then sends done/error event."""

    loop = asyncio.get_running_loop()
    token_q: asyncio.Queue = asyncio.Queue()

    def token_cb(tok: str):
        asyncio.run_coroutine_threadsafe(token_q.put({"type": "content", "msg": tok}), loop)

    def thinking_cb(tok: str):
        asyncio.run_coroutine_threadsafe(token_q.put({"type": "thinking", "msg": tok}), loop)

    system = get_system_prompt(req.base_model)

    async def stream():
        try:
            yield _sse({"step": "start", "msg": "🤖 AI 开始分析建模方案..."})

            if req.engine in {"open3d", "auto"}:
                yield _sse({"step": "building", "msg": "🧬 正在调用开源高精 3D 生成引擎（Hunyuan3D/兼容服务）..."})
                open3d_name = re.sub(r"[^\w\-]", "_", req.prompt[:32] or "open3d_model")
                try:
                    open3d_result = await asyncio.to_thread(generate_open3d_asset, req.prompt, open3d_name)
                    yield _sse({
                        "step":        "done",
                        "msg":         f"✅ 开源高精模型生成完成：{open3d_result['filename']} ({open3d_result['size_kb']} KB)",
                        "filename":    open3d_result["filename"],
                        "model_name":  os.path.splitext(open3d_result["filename"])[0],
                        "description": req.prompt,
                        "parts_count": 0,
                        "size_kb":     open3d_result["size_kb"],
                        "url":         open3d_result["url"],
                        "parts":       [],
                        "tokens":      {"input": 0, "output": 0},
                    })
                    return
                except Open3DGeneratorUnavailable as e:
                    if req.engine == "open3d":
                        yield _sse({"step": "building", "msg": f"⚠️ 开源高精引擎不可用，回退到程序化建模：{e}"})
                    else:
                        yield _sse({"step": "building", "msg": f"⚠️ 开源高精引擎不可用，自动切换到程序化建模：{e}"})

            # Run LLM in thread, stream tokens via queue
            result_holder: dict = {}
            err_holder:    dict = {}

            def run_llm():
                try:
                    set_model(req.model)
                    result_holder["r"] = llm_call(system, req.prompt, ai_model_tool, token_cb=token_cb, thinking_cb=thinking_cb)
                except Exception as e:
                    err_holder["e"] = e
                finally:
                    asyncio.run_coroutine_threadsafe(token_q.put(None), loop)

            import threading
            t = threading.Thread(target=run_llm, daemon=True)
            t.start()

            # Stream tokens as they arrive
            while True:
                tok = await token_q.get()
                if tok is None:
                    break
                if isinstance(tok, dict):
                    if tok["type"] == "thinking":
                        yield _sse({"step": "thinking", "msg": tok["msg"]})
                    else:
                        yield _sse({"step": "token", "msg": tok["msg"]})
                else:
                    yield _sse({"step": "token", "msg": tok})

            if "e" in err_holder:
                yield _sse({"step": "error", "msg": f"LLM 调用失败: {err_holder['e']}"})
                return

            result = result_holder.get("r", {})
            parts  = result.get("parts", [])
            if not parts:
                yield _sse({"step": "error", "msg": "模型生成失败：LLM 未返回零件数据"})
                return

            # Get token usage from AI model generation
            token_usage = get_token_usage()

            yield _sse({"step": "building", "msg": f"🔧 组装 {len(parts)} 个零件 → GLB...", "tokens": token_usage})

            try:
                glb_bytes = await asyncio.to_thread(build_glb, parts)
            except Exception as e:
                yield _sse({"step": "error", "msg": f"GLB 构建失败: {e}"})
                return

            model_name = re.sub(r"[^\w\-]", "_", result.get("model_name", "ai_model"))
            custom_dir = _CATEGORIES["custom"]
            os.makedirs(custom_dir, exist_ok=True)
            filename = f"{model_name}.glb"
            dest = os.path.join(custom_dir, filename)
            with open(dest, "wb") as f:
                f.write(glb_bytes)

            size_kb = len(glb_bytes) // 1024
            yield _sse({
                "step":        "done",
                "msg":         f"✅ 模型生成完成：{filename} ({size_kb} KB)",
                "filename":    filename,
                "model_name":  model_name,
                "description": result.get("description", req.prompt),
                "parts_count": len(parts),
                "size_kb":     size_kb,
                "url":         f"/api/models/custom/{filename}",
                "tokens":      token_usage,
            })

        except Exception as e:
            yield _sse({"step": "error", "msg": str(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Delete a custom model ────────────────────────────────────────────────────

@router.delete("/models/custom/{filename}")
def delete_custom_model(filename: str):
    if not filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only GLB files supported")
    path = os.path.join(_CATEGORIES["custom"], filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(path)
    return {"ok": True}
